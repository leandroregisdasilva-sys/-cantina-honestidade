"""
Sistema de Gestão da Cantina da Honestidade - SENAI Friburgo
Projeto Aplicado II · Equipe 2 · UniSENAI

Executar:
    pip install -r requirements.txt
    python app.py
Depois abrir http://127.0.0.1:5000 no navegador (no Mac, veja o README).
"""
import os
import secrets
from datetime import datetime

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from db import agora, conectar, inicializar_banco
from servicos import saldo
from validacoes import formatar_cpf, formatar_dinheiro, somente_digitos, validar_usuario

app = Flask(__name__)
app.secret_key = os.environ.get("CANTINA_SECRET") or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = 3 * 1024 * 1024     # recusa uploads acima de 3 MB
app.config["PASTA_FOTOS"] = os.path.join(app.root_path, "static", "uploads")

app.jinja_env.filters["cpf"] = formatar_cpf
app.jinja_env.filters["dinheiro"] = formatar_dinheiro


@app.template_filter("data")
def formatar_data(valor, com_hora=True):
    if not valor:
        return ""
    momento = datetime.strptime(str(valor)[:19], "%Y-%m-%d %H:%M:%S")
    return momento.strftime("%d/%m/%Y %H:%M" if com_hora else "%d/%m/%Y")


@app.context_processor
def dados_da_sessao():
    """Disponibiliza o nome, o perfil e o saldo do usuário logado para todas as telas."""
    extra = {"perfil": session.get("perfil"), "nome_logado": session.get("nome")}
    if session.get("perfil") == "usuario":
        with conectar() as cx:
            extra["saldo_logado"] = saldo(cx, session["id"])
        extra["itens_carrinho"] = sum(session.get("carrinho", {}).values())
    return extra


# ------------------------------------------------------------------ autenticação
@app.route("/")
def inicio():
    if session.get("perfil") == "funcionario":
        return redirect(url_for("admin.painel"))
    if session.get("perfil") == "usuario":
        return redirect(url_for("loja.catalogo"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    perfil = request.values.get("perfil", "usuario")
    if perfil not in ("usuario", "funcionario"):
        perfil = "usuario"
    proximo = request.values.get("proximo", "")
    erros = {}

    if request.method == "POST":
        identificacao = request.form.get("login", "").strip()
        senha = request.form.get("senha", "")
        if not identificacao:
            erros["login"] = "Informe sua matrícula, e-mail ou CPF." if perfil == "usuario" \
                else "Informe seu e-mail ou CPF."
        if not senha:
            erros["senha"] = "Informe sua senha."

        if not erros:
            cpf = somente_digitos(identificacao)
            with conectar() as cx:
                if perfil == "usuario":
                    pessoa = cx.execute(
                        """SELECT id_usuario AS id, nome, senha, ativo FROM usuario
                           WHERE upper(matricula) = upper(?) OR lower(email) = lower(?) OR cpf = ?""",
                        (identificacao, identificacao, cpf or "-")).fetchone()
                else:
                    pessoa = cx.execute(
                        """SELECT id_funcionario AS id, nome, senha, ativo FROM funcionario
                           WHERE lower(email) = lower(?) OR cpf = ?""",
                        (identificacao, cpf or "-")).fetchone()

            if pessoa is None or not check_password_hash(pessoa["senha"], senha):
                flash("Login ou senha incorretos.", "erro")
            elif not pessoa["ativo"]:
                flash("Este cadastro está inativo. Procure a equipe da cantina.", "erro")
            else:
                session.clear()
                session.update(perfil=perfil, id=pessoa["id"], nome=pessoa["nome"], carrinho={})
                flash(f"Olá, {pessoa['nome'].split()[0]}!", "sucesso")
                destino_padrao = url_for("admin.painel") if perfil == "funcionario" else url_for("loja.catalogo")
                prefixo = "/admin" if perfil == "funcionario" else "/loja"
                destino = proximo if proximo.startswith(prefixo) else destino_padrao
                return redirect(destino)
        else:
            flash("Preencha os campos destacados.", "erro")

    return render_template("auth/login.html", perfil_login=perfil, erros=erros,
                           login_digitado=request.form.get("login", ""), proximo=proximo)


@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    """Autocadastro do consumidor (RF01)."""
    if request.method == "POST":
        with conectar() as cx:
            erros, dados = validar_usuario(request.form, cx)
            if not erros:
                id_novo = cx.execute(
                    """INSERT INTO usuario (nome, matricula, email, cpf, senha, data_cadastro)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (dados["nome"], dados["matricula"], dados["email"], dados["cpf"],
                     generate_password_hash(dados["senha"]), agora())).lastrowid
                session.clear()
                session.update(perfil="usuario", id=id_novo, nome=dados["nome"], carrinho={})
                flash("Cadastro feito! Adicione créditos na carteira para comprar.", "sucesso")
                return redirect(url_for("loja.carteira"))
        flash("Corrija os campos destacados para criar sua conta.", "erro")
        return render_template("auth/cadastro.html", usuario=request.form, erros=erros), 400
    return render_template("auth/cadastro.html", usuario={}, erros={})


@app.route("/sair")
def sair():
    session.clear()
    flash("Você saiu do sistema.", "sucesso")
    return redirect(url_for("login"))


@app.errorhandler(404)
def nao_encontrado(_erro):
    return render_template("erro.html", titulo="Página não encontrada",
                           mensagem="O endereço não existe ou o registro foi removido."), 404


@app.errorhandler(413)
def arquivo_grande(_erro):
    flash("O arquivo enviado é grande demais. A foto pode ter até 2 MB.", "erro")
    return redirect(request.referrer or url_for("inicio"))


# ------------------------------------------------------------------ módulos
from admin import bp as bp_admin      # noqa: E402  (importa depois de criar o app)
from loja import bp as bp_loja        # noqa: E402

app.register_blueprint(bp_admin)
app.register_blueprint(bp_loja)

inicializar_banco()

if __name__ == "__main__":
    porta = int(os.environ.get("PORT", 5000))
    app.run(debug=True, port=porta)
