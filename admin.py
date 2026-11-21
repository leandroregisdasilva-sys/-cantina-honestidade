"""Painel administrativo, usado pelos funcionários da cantina.

Usuários (RF01), produtos (RF02), recarga em dinheiro (RF03), relatórios (RF05),
funcionários (RF06), entrada de estoque (RF07) e QR Codes dos produtos (RF04).
"""
import os
import uuid
from datetime import date, datetime

import qrcode
import qrcode.image.svg
from flask import (Blueprint, abort, current_app, flash, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import generate_password_hash

from acesso import login_obrigatorio
from db import agora, conectar
from servicos import registrar_recarga, saldo
from validacoes import (QTD_MAX, formatar_cpf, formatar_dinheiro, validar_entrada_estoque,
                        validar_funcionario, validar_produto, validar_recarga, validar_usuario)

bp = Blueprint("admin", __name__, url_prefix="/admin")
ESTOQUE_BAIXO = 5


@bp.before_request
@login_obrigatorio("funcionario")
def exigir_funcionario():
    """Toda rota deste módulo exige login de funcionário."""
    return None


def buscar(conexao, tabela, chave, valor):
    registro = conexao.execute(f"SELECT * FROM {tabela} WHERE {chave} = ?", (valor,)).fetchone()
    if registro is None:
        abort(404)
    return registro


# ------------------------------------------------------------------ painel
@bp.route("/")
def painel():
    hoje = date.today().isoformat()
    inicio_mes = date.today().replace(day=1).isoformat()
    with conectar() as cx:
        vendas_hoje = cx.execute(
            "SELECT COUNT(*) AS qtd, COALESCE(SUM(valor_total), 0) AS total FROM venda WHERE date(data_hora) = ?",
            (hoje,)).fetchone()
        vendas_mes = cx.execute(
            "SELECT COUNT(*) AS qtd, COALESCE(SUM(valor_total), 0) AS total FROM venda WHERE date(data_hora) >= ?",
            (inicio_mes,)).fetchone()
        saldo_carteiras = cx.execute(
            """SELECT COALESCE(SUM(CASE WHEN tipo_transacao = 'CREDITO' THEN valor ELSE -valor END), 0)
               FROM transacao_carteira""").fetchone()[0]
        usuarios_ativos = cx.execute("SELECT COUNT(*) FROM usuario WHERE ativo = 1").fetchone()[0]
        estoque_baixo = cx.execute(
            "SELECT * FROM produto WHERE ativo = 1 AND quantidade_estoque < ? ORDER BY quantidade_estoque",
            (ESTOQUE_BAIXO,)).fetchall()
        ultimas_vendas = cx.execute(
            """SELECT v.*, u.nome FROM venda v JOIN usuario u ON u.id_usuario = v.id_usuario
               ORDER BY v.data_hora DESC LIMIT 6""").fetchall()
    return render_template("admin/painel.html", vendas_hoje=vendas_hoje, vendas_mes=vendas_mes,
                           saldo_carteiras=saldo_carteiras, usuarios_ativos=usuarios_ativos,
                           estoque_baixo=estoque_baixo, ultimas_vendas=ultimas_vendas,
                           limite_baixo=ESTOQUE_BAIXO)


# ------------------------------------------------------------------ situação (exclusão lógica)
def mudar_situacao(tabela, chave, id_registro, ativo, rotulo, destino, nome_coluna="nome"):
    with conectar() as cx:
        registro = buscar(cx, tabela, chave, id_registro)
        cx.execute(f"UPDATE {tabela} SET ativo = ? WHERE {chave} = ?", (ativo, id_registro))
    acao = "reativado" if ativo else "inativado"
    flash(f"{rotulo} {registro[nome_coluna]} {acao} com sucesso.", "sucesso")
    return redirect(url_for(destino, situacao="ativos" if ativo else "inativos"))


def filtro_situacao(situacao):
    return {"ativos": " AND ativo = 1", "inativos": " AND ativo = 0"}.get(situacao, "")


# ------------------------------------------------------------------ usuários (RF01)
@bp.route("/usuarios")
def usuarios():
    busca = request.args.get("busca", "").strip()
    situacao = request.args.get("situacao", "ativos")
    sql = "SELECT * FROM usuario WHERE 1 = 1" + filtro_situacao(situacao)
    parametros = []
    if busca:
        termo = f"%{busca}%"
        digitos = "".join(c for c in busca if c.isdigit())
        sql += " AND (nome LIKE ? OR matricula LIKE ? OR email LIKE ? OR cpf LIKE ?)"
        parametros += [termo, termo, termo, f"%{digitos}%" if digitos else termo]
    with conectar() as cx:
        lista = cx.execute(sql + " ORDER BY nome", parametros).fetchall()
        saldos = {u["id_usuario"]: saldo(cx, u["id_usuario"]) for u in lista}
        totais = cx.execute("SELECT SUM(ativo = 1) AS ativos, SUM(ativo = 0) AS inativos FROM usuario").fetchone()
    return render_template("admin/usuarios.html", usuarios=lista, saldos=saldos, busca=busca,
                           situacao=situacao, totais=totais)


@bp.route("/usuarios/novo", methods=["GET", "POST"])
def usuario_novo():
    if request.method == "POST":
        with conectar() as cx:
            erros, dados = validar_usuario(request.form, cx)
            if not erros:
                cx.execute(
                    """INSERT INTO usuario (nome, matricula, email, cpf, senha, data_cadastro)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (dados["nome"], dados["matricula"], dados["email"], dados["cpf"],
                     generate_password_hash(dados["senha"]), agora()))
                flash(f"Usuário {dados['nome']} cadastrado com sucesso.", "sucesso")
                return redirect(url_for("admin.usuarios"))
        flash("Corrija os campos destacados para salvar.", "erro")
        return render_template("admin/usuario_form.html", usuario=request.form, erros=erros, novo=True), 400
    return render_template("admin/usuario_form.html", usuario={}, erros={}, novo=True)


@bp.route("/usuarios/<int:id_usuario>/editar", methods=["GET", "POST"])
def usuario_editar(id_usuario):
    with conectar() as cx:
        atual = buscar(cx, "usuario", "id_usuario", id_usuario)
        if request.method == "POST":
            erros, dados = validar_usuario(request.form, cx, id_usuario=id_usuario)
            if not erros:
                campos = "nome = ?, matricula = ?, email = ?, cpf = ?"
                valores = [dados["nome"], dados["matricula"], dados["email"], dados["cpf"]]
                if dados["senha"]:
                    campos += ", senha = ?"
                    valores.append(generate_password_hash(dados["senha"]))
                cx.execute(f"UPDATE usuario SET {campos} WHERE id_usuario = ?", valores + [id_usuario])
                flash(f"Dados de {dados['nome']} alterados com sucesso.", "sucesso")
                return redirect(url_for("admin.usuarios"))
            flash("Corrija os campos destacados para salvar.", "erro")
            formulario = dict(request.form, id_usuario=id_usuario)
            return render_template("admin/usuario_form.html", usuario=formulario, erros=erros, novo=False), 400
    usuario = dict(atual, cpf=formatar_cpf(atual["cpf"]))
    return render_template("admin/usuario_form.html", usuario=usuario, erros={}, novo=False)


@bp.route("/usuarios/<int:id_usuario>/inativar", methods=["POST"])
def usuario_inativar(id_usuario):
    return mudar_situacao("usuario", "id_usuario", id_usuario, 0, "Usuário", "admin.usuarios")


@bp.route("/usuarios/<int:id_usuario>/reativar", methods=["POST"])
def usuario_reativar(id_usuario):
    return mudar_situacao("usuario", "id_usuario", id_usuario, 1, "Usuário", "admin.usuarios")


@bp.route("/usuarios/<int:id_usuario>/recarga", methods=["GET", "POST"])
def usuario_recarga(id_usuario):
    """Recarga em dinheiro feita no balcão: grava o funcionário responsável (RF03)."""
    with conectar() as cx:
        usuario = buscar(cx, "usuario", "id_usuario", id_usuario)
        if not usuario["ativo"]:
            flash("Reative o usuário antes de adicionar créditos.", "erro")
            return redirect(url_for("admin.usuarios"))
        erros, valor_digitado = {}, ""
        if request.method == "POST":
            erros, dados = validar_recarga(request.form)
            valor_digitado = request.form.get("valor", "")
            if not erros:
                registrar_recarga(cx, id_usuario, dados["valor"], id_funcionario=session["id"])
                flash(f"Recarga de {formatar_dinheiro(dados['valor'])} registrada para {usuario['nome']}.", "sucesso")
                return redirect(url_for("admin.usuarios"))
            flash("Corrija o valor da recarga.", "erro")
        saldo_atual = saldo(cx, id_usuario)
        extrato = cx.execute(
            """SELECT t.*, f.nome AS funcionario FROM transacao_carteira t
               LEFT JOIN funcionario f ON f.id_funcionario = t.id_funcionario
               WHERE t.id_usuario = ? ORDER BY t.data_hora DESC LIMIT 8""", (id_usuario,)).fetchall()
    return render_template("admin/recarga.html", usuario=usuario, saldo_atual=saldo_atual,
                           extrato=extrato, erros=erros, valor=valor_digitado), (400 if erros else 200)


# ------------------------------------------------------------------ funcionários (RF06)
@bp.route("/funcionarios")
def funcionarios():
    situacao = request.args.get("situacao", "ativos")
    with conectar() as cx:
        lista = cx.execute("SELECT * FROM funcionario WHERE 1 = 1" + filtro_situacao(situacao)
                           + " ORDER BY nome").fetchall()
    return render_template("admin/funcionarios.html", funcionarios=lista, situacao=situacao)


@bp.route("/funcionarios/novo", methods=["GET", "POST"])
def funcionario_novo():
    if request.method == "POST":
        with conectar() as cx:
            erros, dados = validar_funcionario(request.form, cx)
            if not erros:
                cx.execute("INSERT INTO funcionario (nome, cpf, email, senha, cargo) VALUES (?, ?, ?, ?, ?)",
                           (dados["nome"], dados["cpf"], dados["email"],
                            generate_password_hash(dados["senha"]), dados["cargo"]))
                flash(f"Funcionário {dados['nome']} cadastrado com sucesso.", "sucesso")
                return redirect(url_for("admin.funcionarios"))
        flash("Corrija os campos destacados para salvar.", "erro")
        return render_template("admin/funcionario_form.html", funcionario=request.form, erros=erros, novo=True), 400
    return render_template("admin/funcionario_form.html", funcionario={}, erros={}, novo=True)


@bp.route("/funcionarios/<int:id_funcionario>/editar", methods=["GET", "POST"])
def funcionario_editar(id_funcionario):
    with conectar() as cx:
        atual = buscar(cx, "funcionario", "id_funcionario", id_funcionario)
        if request.method == "POST":
            erros, dados = validar_funcionario(request.form, cx, id_funcionario=id_funcionario)
            if not erros:
                campos = "nome = ?, cpf = ?, email = ?, cargo = ?"
                valores = [dados["nome"], dados["cpf"], dados["email"], dados["cargo"]]
                if dados["senha"]:
                    campos += ", senha = ?"
                    valores.append(generate_password_hash(dados["senha"]))
                cx.execute(f"UPDATE funcionario SET {campos} WHERE id_funcionario = ?", valores + [id_funcionario])
                if id_funcionario == session["id"]:
                    session["nome"] = dados["nome"]
                flash(f"Dados de {dados['nome']} alterados com sucesso.", "sucesso")
                return redirect(url_for("admin.funcionarios"))
            flash("Corrija os campos destacados para salvar.", "erro")
            formulario = dict(request.form, id_funcionario=id_funcionario)
            return render_template("admin/funcionario_form.html", funcionario=formulario, erros=erros, novo=False), 400
    funcionario = dict(atual, cpf=formatar_cpf(atual["cpf"]))
    return render_template("admin/funcionario_form.html", funcionario=funcionario, erros={}, novo=False)


@bp.route("/funcionarios/<int:id_funcionario>/inativar", methods=["POST"])
def funcionario_inativar(id_funcionario):
    if id_funcionario == session["id"]:
        flash("Você não pode inativar o seu próprio cadastro.", "erro")
        return redirect(url_for("admin.funcionarios"))
    with conectar() as cx:
        ativos = cx.execute("SELECT COUNT(*) FROM funcionario WHERE ativo = 1").fetchone()[0]
    if ativos <= 1:
        flash("A cantina precisa de pelo menos um funcionário ativo.", "erro")
        return redirect(url_for("admin.funcionarios"))
    return mudar_situacao("funcionario", "id_funcionario", id_funcionario, 0, "Funcionário", "admin.funcionarios")


@bp.route("/funcionarios/<int:id_funcionario>/reativar", methods=["POST"])
def funcionario_reativar(id_funcionario):
    return mudar_situacao("funcionario", "id_funcionario", id_funcionario, 1, "Funcionário", "admin.funcionarios")


# ------------------------------------------------------------------ produtos (RF02)
def salvar_foto(arquivo):
    extensao = os.path.splitext(arquivo.filename)[1].lower().replace(".jpeg", ".jpg")
    nome = f"produto_{uuid.uuid4().hex[:12]}{extensao}"
    arquivo.save(os.path.join(current_app.config["PASTA_FOTOS"], nome))
    return nome


@bp.route("/produtos")
def produtos():
    busca = request.args.get("busca", "").strip()
    situacao = request.args.get("situacao", "ativos")
    sql = "SELECT * FROM produto WHERE 1 = 1" + filtro_situacao(situacao)
    parametros = []
    if busca:
        sql += " AND descricao LIKE ?"
        parametros.append(f"%{busca}%")
    with conectar() as cx:
        lista = cx.execute(sql + " ORDER BY descricao", parametros).fetchall()
    return render_template("admin/produtos.html", produtos=lista, busca=busca, situacao=situacao,
                           limite_baixo=ESTOQUE_BAIXO)


@bp.route("/produtos/novo", methods=["GET", "POST"])
def produto_novo():
    if request.method == "POST":
        foto = request.files.get("foto")
        with conectar() as cx:
            erros, dados = validar_produto(request.form, foto, cx)
            if not erros:
                nome_foto = salvar_foto(foto) if foto and foto.filename else None
                id_produto = cx.execute(
                    """INSERT INTO produto (id_funcionario, descricao, preco, foto_url, quantidade_estoque)
                       VALUES (?, ?, ?, ?, ?)""",
                    (session["id"], dados["descricao"], float(dados["preco"]), nome_foto, dados["estoque"])).lastrowid
                if dados["estoque"]:
                    cx.execute("INSERT INTO entrada_estoque (id_produto, id_funcionario, quantidade, data_hora) "
                               "VALUES (?, ?, ?, ?)", (id_produto, session["id"], dados["estoque"], agora()))
                flash(f"Produto {dados['descricao']} cadastrado com sucesso.", "sucesso")
                return redirect(url_for("admin.produtos"))
        flash("Corrija os campos destacados para salvar.", "erro")
        return render_template("admin/produto_form.html", produto=request.form, erros=erros, novo=True), 400
    return render_template("admin/produto_form.html", produto={}, erros={}, novo=True)


@bp.route("/produtos/<int:id_produto>/editar", methods=["GET", "POST"])
def produto_editar(id_produto):
    with conectar() as cx:
        atual = buscar(cx, "produto", "id_produto", id_produto)
        if request.method == "POST":
            foto = request.files.get("foto")
            erros, dados = validar_produto(request.form, foto, cx, id_produto=id_produto)
            if not erros:
                nome_foto = salvar_foto(foto) if foto and foto.filename else atual["foto_url"]
                cx.execute("UPDATE produto SET descricao = ?, preco = ?, foto_url = ? WHERE id_produto = ?",
                           (dados["descricao"], float(dados["preco"]), nome_foto, id_produto))
                flash(f"Produto {dados['descricao']} alterado com sucesso.", "sucesso")
                return redirect(url_for("admin.produtos"))
            flash("Corrija os campos destacados para salvar.", "erro")
            formulario = dict(request.form, id_produto=id_produto, foto_url=atual["foto_url"],
                              quantidade_estoque=atual["quantidade_estoque"])
            return render_template("admin/produto_form.html", produto=formulario, erros=erros, novo=False), 400
    produto = dict(atual, preco=formatar_dinheiro(atual["preco"]))
    return render_template("admin/produto_form.html", produto=produto, erros={}, novo=False)


@bp.route("/produtos/<int:id_produto>/inativar", methods=["POST"])
def produto_inativar(id_produto):
    return mudar_situacao("produto", "id_produto", id_produto, 0, "Produto", "admin.produtos", "descricao")


@bp.route("/produtos/<int:id_produto>/reativar", methods=["POST"])
def produto_reativar(id_produto):
    return mudar_situacao("produto", "id_produto", id_produto, 1, "Produto", "admin.produtos", "descricao")


@bp.route("/produtos/qrcodes")
def qrcodes():
    """Página para imprimir os QR Codes: o consumidor aponta a câmera e vai direto ao produto."""
    with conectar() as cx:
        lista = cx.execute("SELECT * FROM produto WHERE ativo = 1 ORDER BY descricao").fetchall()
    codigos = []
    for produto in lista:
        endereco = url_for("loja.produto", id_produto=produto["id_produto"], _external=True)
        imagem = qrcode.make(endereco, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
        codigos.append((produto, imagem.to_string(encoding="unicode"), endereco))
    return render_template("admin/qrcodes.html", codigos=codigos)


# ------------------------------------------------------------------ estoque (RF07)
@bp.route("/estoque", methods=["GET", "POST"])
def estoque():
    erros, formulario = {}, {}
    with conectar() as cx:
        if request.method == "POST":
            formulario = request.form
            erros, dados = validar_entrada_estoque(request.form, cx)
            if not erros:
                cx.execute("INSERT INTO entrada_estoque (id_produto, id_funcionario, quantidade, data_hora) "
                           "VALUES (?, ?, ?, ?)", (dados["id_produto"], session["id"], dados["quantidade"], agora()))
                cx.execute("UPDATE produto SET quantidade_estoque = quantidade_estoque + ? WHERE id_produto = ?",
                           (dados["quantidade"], dados["id_produto"]))
                produto = buscar(cx, "produto", "id_produto", dados["id_produto"])
                flash(f"Entrada de {dados['quantidade']} unidade(s) de {produto['descricao']} registrada. "
                      f"Estoque atual: {produto['quantidade_estoque']}.", "sucesso")
                return redirect(url_for("admin.estoque"))
            flash("Corrija os campos destacados para registrar a entrada.", "erro")
        produtos_ativos = cx.execute("SELECT * FROM produto WHERE ativo = 1 ORDER BY descricao").fetchall()
        entradas = cx.execute(
            """SELECT e.*, p.descricao, f.nome AS funcionario FROM entrada_estoque e
               JOIN produto p ON p.id_produto = e.id_produto
               JOIN funcionario f ON f.id_funcionario = e.id_funcionario
               ORDER BY e.data_hora DESC LIMIT 30""").fetchall()
    return render_template("admin/estoque.html", produtos=produtos_ativos, entradas=entradas, erros=erros,
                           formulario=formulario, qtd_max=QTD_MAX, limite_baixo=ESTOQUE_BAIXO), (400 if erros else 200)


# ------------------------------------------------------------------ relatórios (RF05)
@bp.route("/relatorios")
def relatorios():
    hoje = date.today()
    de_txt = request.args.get("de") or hoje.replace(day=1).isoformat()
    ate_txt = request.args.get("ate") or hoje.isoformat()
    erros = {}
    try:
        de = datetime.strptime(de_txt, "%Y-%m-%d").date()
    except ValueError:
        erros["de"], de = "Data inicial inválida.", hoje.replace(day=1)
    try:
        ate = datetime.strptime(ate_txt, "%Y-%m-%d").date()
    except ValueError:
        erros["ate"], ate = "Data final inválida.", hoje
    if not erros and de > ate:
        erros["ate"] = "A data final deve ser igual ou posterior à inicial."
        de, ate = ate, de
    periodo = (de.isoformat(), ate.isoformat())

    with conectar() as cx:
        resumo = cx.execute(
            """SELECT COUNT(*) AS vendas, COALESCE(SUM(valor_total), 0) AS total,
                      COALESCE(AVG(valor_total), 0) AS ticket
               FROM venda WHERE date(data_hora) BETWEEN ? AND ?""", periodo).fetchone()
        mais_vendidos = cx.execute(
            """SELECT p.descricao, SUM(i.quantidade) AS unidades, SUM(i.quantidade * i.preco_unitario) AS valor
               FROM item_venda i JOIN venda v ON v.id_venda = i.id_venda
               JOIN produto p ON p.id_produto = i.id_produto
               WHERE date(v.data_hora) BETWEEN ? AND ?
               GROUP BY p.id_produto ORDER BY unidades DESC, valor DESC""", periodo).fetchall()
        carteira = cx.execute(
            """SELECT
                 COALESCE(SUM(CASE WHEN tipo_transacao = 'CREDITO' AND id_funcionario IS NOT NULL THEN valor END), 0) AS dinheiro,
                 COALESCE(SUM(CASE WHEN tipo_transacao = 'CREDITO' AND id_funcionario IS NULL THEN valor END), 0) AS online,
                 COALESCE(SUM(CASE WHEN tipo_transacao = 'DEBITO' THEN valor END), 0) AS debitos
               FROM transacao_carteira WHERE date(data_hora) BETWEEN ? AND ?""", periodo).fetchone()
        consumo = cx.execute(
            """SELECT u.nome, u.matricula, COUNT(v.id_venda) AS compras, SUM(v.valor_total) AS total
               FROM venda v JOIN usuario u ON u.id_usuario = v.id_usuario
               WHERE date(v.data_hora) BETWEEN ? AND ?
               GROUP BY u.id_usuario ORDER BY total DESC""", periodo).fetchall()
        vendas = cx.execute(
            """SELECT v.*, u.nome FROM venda v JOIN usuario u ON u.id_usuario = v.id_usuario
               WHERE date(v.data_hora) BETWEEN ? AND ? ORDER BY v.data_hora DESC""", periodo).fetchall()
    if erros:
        flash("Confira as datas do período.", "erro")
    return render_template("admin/relatorios.html", de=periodo[0], ate=periodo[1], erros=erros, resumo=resumo,
                           mais_vendidos=mais_vendidos, carteira=carteira, consumo=consumo, vendas=vendas)
