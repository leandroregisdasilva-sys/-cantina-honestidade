"""Autoatendimento do consumidor: catálogo, carrinho, compra (RF04), carteira (RF03) e histórico (RF05)."""
from decimal import Decimal

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from acesso import login_obrigatorio
from db import conectar
from servicos import ErroNegocio, registrar_compra, registrar_recarga, saldo
from validacoes import formatar_dinheiro, ler_inteiro, validar_recarga

bp = Blueprint("loja", __name__, url_prefix="/loja")
QTD_MAX_ITEM = 20


@bp.before_request
@login_obrigatorio("usuario")
def exigir_usuario():
    return None


def carrinho():
    """O carrinho fica na sessão como {"id_produto": quantidade}."""
    return session.setdefault("carrinho", {})


def salvar_carrinho(itens):
    session["carrinho"] = {k: v for k, v in itens.items() if v > 0}
    session.modified = True


# ------------------------------------------------------------------ catálogo
@bp.route("/")
def catalogo():
    busca = request.args.get("busca", "").strip()
    sql = "SELECT * FROM produto WHERE ativo = 1"
    parametros = []
    if busca:
        sql += " AND descricao LIKE ?"
        parametros.append(f"%{busca}%")
    with conectar() as cx:
        produtos = cx.execute(sql + " ORDER BY quantidade_estoque = 0, descricao", parametros).fetchall()
    return render_template("loja/catalogo.html", produtos=produtos, busca=busca, no_carrinho=carrinho())


@bp.route("/produto/<int:id_produto>")
def produto(id_produto):
    """Destino do QR Code colado na prateleira."""
    with conectar() as cx:
        item = cx.execute("SELECT * FROM produto WHERE id_produto = ? AND ativo = 1", (id_produto,)).fetchone()
    if item is None:
        abort(404)
    return render_template("loja/produto.html", produto=item, no_carrinho=carrinho().get(str(id_produto), 0))


# ------------------------------------------------------------------ carrinho
@bp.route("/carrinho/adicionar/<int:id_produto>", methods=["POST"])
def adicionar(id_produto):
    quantidade = ler_inteiro(request.form.get("quantidade", "1"))
    destino = request.form.get("voltar") or url_for("loja.catalogo")
    if not destino.startswith("/loja"):
        destino = url_for("loja.catalogo")
    with conectar() as cx:
        item = cx.execute("SELECT * FROM produto WHERE id_produto = ? AND ativo = 1", (id_produto,)).fetchone()
    if item is None:
        flash("Este produto não está mais disponível.", "erro")
        return redirect(destino)
    if quantidade is None or quantidade < 1:
        flash("Informe uma quantidade inteira, a partir de 1.", "erro")
        return redirect(destino)

    itens = carrinho()
    nova = itens.get(str(id_produto), 0) + quantidade
    limite = min(item["quantidade_estoque"], QTD_MAX_ITEM)
    if nova > limite:
        flash(f"Só é possível levar {limite} unidade(s) de {item['descricao']}.", "erro")
        return redirect(destino)
    itens[str(id_produto)] = nova
    salvar_carrinho(itens)
    flash(f"{quantidade} × {item['descricao']} no carrinho.", "sucesso")
    return redirect(destino)


@bp.route("/carrinho")
def ver_carrinho():
    itens, total, avisos = [], Decimal("0.00"), []
    with conectar() as cx:
        for id_txt, quantidade in list(carrinho().items()):
            item = cx.execute("SELECT * FROM produto WHERE id_produto = ?", (int(id_txt),)).fetchone()
            if item is None or not item["ativo"]:
                avisos.append("Um produto saiu do catálogo e foi removido do carrinho.")
                itens_atuais = carrinho()
                itens_atuais.pop(id_txt, None)
                salvar_carrinho(itens_atuais)
                continue
            subtotal = Decimal(str(item["preco"])) * quantidade
            total += subtotal
            itens.append({"produto": item, "quantidade": quantidade, "subtotal": subtotal})
        saldo_atual = saldo(cx, session["id"])
    for aviso in avisos:
        flash(aviso, "erro")
    return render_template("loja/carrinho.html", itens=itens, total=total, saldo_atual=saldo_atual,
                           falta=max(total - saldo_atual, Decimal("0")), qtd_max=QTD_MAX_ITEM)


@bp.route("/carrinho/alterar/<int:id_produto>", methods=["POST"])
def alterar(id_produto):
    quantidade = ler_inteiro(request.form.get("quantidade", ""))
    itens = carrinho()
    if str(id_produto) not in itens:
        return redirect(url_for("loja.ver_carrinho"))
    if quantidade is None:
        flash("Informe uma quantidade inteira.", "erro")
        return redirect(url_for("loja.ver_carrinho"))
    with conectar() as cx:
        item = cx.execute("SELECT * FROM produto WHERE id_produto = ?", (id_produto,)).fetchone()
    limite = min(item["quantidade_estoque"], QTD_MAX_ITEM)
    if quantidade > limite:
        flash(f"Só é possível levar {limite} unidade(s) de {item['descricao']}.", "erro")
        return redirect(url_for("loja.ver_carrinho"))
    itens[str(id_produto)] = quantidade
    salvar_carrinho(itens)
    flash("Item removido do carrinho." if quantidade == 0 else "Quantidade atualizada.", "sucesso")
    return redirect(url_for("loja.ver_carrinho"))


@bp.route("/carrinho/finalizar", methods=["POST"])
def finalizar():
    pedido = {int(k): v for k, v in carrinho().items()}
    try:
        with conectar() as cx:
            id_venda, total = registrar_compra(cx, session["id"], pedido)
    except ErroNegocio as erro:
        flash(str(erro), "erro")
        return redirect(url_for("loja.ver_carrinho"))
    salvar_carrinho({})
    flash(f"Compra nº {id_venda} registrada: {formatar_dinheiro(total)} descontados da sua carteira. "
          "Obrigado pela honestidade!", "sucesso")
    return redirect(url_for("loja.compras"))


# ------------------------------------------------------------------ carteira (RF03)
@bp.route("/carteira", methods=["GET", "POST"])
def carteira():
    erros, valor_digitado = {}, ""
    with conectar() as cx:
        if request.method == "POST":
            erros, dados = validar_recarga(request.form)
            valor_digitado = request.form.get("valor", "")
            if not erros:
                registrar_recarga(cx, session["id"], dados["valor"])          # recarga online: sem funcionário
                flash(f"Recarga de {formatar_dinheiro(dados['valor'])} confirmada.", "sucesso")
                return redirect(url_for("loja.carteira"))
            flash("Corrija o valor da recarga.", "erro")
        saldo_atual = saldo(cx, session["id"])
        extrato = cx.execute(
            """SELECT t.*, f.nome AS funcionario FROM transacao_carteira t
               LEFT JOIN funcionario f ON f.id_funcionario = t.id_funcionario
               WHERE t.id_usuario = ? ORDER BY t.data_hora DESC, t.id_transacao DESC""",
            (session["id"],)).fetchall()
    return render_template("loja/carteira.html", saldo_atual=saldo_atual, extrato=extrato,
                           erros=erros, valor=valor_digitado), (400 if erros else 200)


# ------------------------------------------------------------------ histórico (RF05)
@bp.route("/compras")
def compras():
    with conectar() as cx:
        vendas = cx.execute("SELECT * FROM venda WHERE id_usuario = ? ORDER BY data_hora DESC, id_venda DESC",
                            (session["id"],)).fetchall()
        itens = {}
        for venda in vendas:
            itens[venda["id_venda"]] = cx.execute(
                """SELECT i.*, p.descricao FROM item_venda i JOIN produto p ON p.id_produto = i.id_produto
                   WHERE i.id_venda = ?""", (venda["id_venda"],)).fetchall()
    return render_template("loja/compras.html", vendas=vendas, itens=itens)
