"""Regras de validação dos formulários: obrigatoriedade, tipos de dados e formatos.

Cada função devolve (erros, dados_limpos). `erros` é um dicionário {campo: mensagem};
vazio significa que os dados podem ser gravados.
"""
import os
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

REGEX_EMAIL = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")
REGEX_NOME = re.compile(r"^[A-Za-zÀ-ÿ'. ]+$")
REGEX_MATRICULA = re.compile(r"^[A-Za-z0-9]{3,20}$")
EXTENSOES_FOTO = {".png", ".jpg", ".jpeg", ".webp"}
TAMANHO_MAX_FOTO = 2 * 1024 * 1024          # 2 MB

PRECO_MAX = Decimal("999.99")
RECARGA_MIN, RECARGA_MAX = Decimal("1.00"), Decimal("500.00")
QTD_MAX = 9999


# ---------------------------------------------------------------- conversões
def somente_digitos(texto):
    return re.sub(r"\D", "", texto or "")


def cpf_valido(cpf):
    """Valida o CPF pelos dois dígitos verificadores."""
    cpf = somente_digitos(cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for posicao in (9, 10):
        soma = sum(int(cpf[i]) * (posicao + 1 - i) for i in range(posicao))
        if (soma * 10) % 11 % 10 != int(cpf[posicao]):
            return False
    return True


def formatar_cpf(cpf):
    cpf = somente_digitos(cpf)
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}" if len(cpf) == 11 else cpf


def ler_dinheiro(texto):
    """Converte 'R$ 1.234,56', '1234,56' ou '1234.56' em Decimal. Devolve None se inválido."""
    if texto is None:
        return None
    texto = str(texto).strip().replace("R$", "").replace(" ", "")
    if not texto:
        return None
    if "," in texto:                       # padrão brasileiro: ponto separa milhar
        texto = texto.replace(".", "").replace(",", ".")
    try:
        valor = Decimal(texto)
    except InvalidOperation:
        return None
    if not valor.is_finite():
        return None
    return valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def formatar_dinheiro(valor):
    valor = Decimal(str(valor or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    inteiro, centavos = f"{abs(valor):.2f}".split(".")
    inteiro = f"{int(inteiro):,}".replace(",", ".")
    sinal = "-" if valor < 0 else ""
    return f"{sinal}R$ {inteiro},{centavos}"


def ler_inteiro(texto):
    texto = (texto or "").strip()
    if not re.fullmatch(r"\d+", texto):
        return None
    return int(texto)


# ---------------------------------------------------------------- regras comuns
def _validar_nome(nome, erros):
    if not nome:
        erros["nome"] = "Informe o nome completo."
    elif len(nome) < 3 or len(nome.split()) < 2:
        erros["nome"] = "Informe nome e sobrenome."
    elif len(nome) > 100:
        erros["nome"] = "O nome pode ter até 100 caracteres."
    elif not REGEX_NOME.match(nome):
        erros["nome"] = "O nome deve conter apenas letras."


def _validar_email(email, erros):
    if not email:
        erros["email"] = "Informe o e-mail."
    elif len(email) > 100 or not REGEX_EMAIL.match(email):
        erros["email"] = "Informe um e-mail válido, por exemplo nome@senai.br."


def _validar_cpf(cpf, erros):
    if not cpf:
        erros["cpf"] = "Informe o CPF."
    elif not cpf_valido(cpf):
        erros["cpf"] = "CPF inválido. Confira os números digitados."


def _validar_senha(dados, erros, obrigatoria):
    senha = dados.get("senha", "")
    confirmacao = dados.get("confirmar_senha", "")
    if obrigatoria or senha:
        if not senha:
            erros["senha"] = "Informe uma senha."
        elif len(senha) < 6:
            erros["senha"] = "A senha deve ter pelo menos 6 caracteres."
        elif len(senha) > 72:
            erros["senha"] = "A senha pode ter até 72 caracteres."
        elif senha != confirmacao:
            erros["confirmar_senha"] = "As senhas não conferem."
    return senha


def _checar_unicos(conexao, tabela, chave_id, id_registro, campos, erros):
    """campos: {coluna: (valor, mensagem)}. Acusa valor repetido em outro registro."""
    for coluna, (valor, mensagem) in campos.items():
        if coluna in erros or not valor:
            continue
        repetido = conexao.execute(
            f"SELECT 1 FROM {tabela} WHERE {coluna} = ? AND {chave_id} != ?",
            (valor, id_registro or 0),
        ).fetchone()
        if repetido:
            erros[coluna] = mensagem


# ---------------------------------------------------------------- usuário
def validar_usuario(dados, conexao, id_usuario=None):
    erros = {}
    nome = dados.get("nome", "").strip()
    matricula = dados.get("matricula", "").strip().upper()
    email = dados.get("email", "").strip().lower()
    cpf = somente_digitos(dados.get("cpf"))

    _validar_nome(nome, erros)
    if not matricula:
        erros["matricula"] = "Informe a matrícula."
    elif not REGEX_MATRICULA.match(matricula):
        erros["matricula"] = "Use de 3 a 20 letras ou números, sem espaços."
    _validar_email(email, erros)
    _validar_cpf(cpf, erros)
    senha = _validar_senha(dados, erros, obrigatoria=id_usuario is None)

    _checar_unicos(conexao, "usuario", "id_usuario", id_usuario, {
        "matricula": (matricula, "Esta matrícula já está cadastrada para outro usuário."),
        "email": (email, "Este e-mail já está cadastrado para outro usuário."),
        "cpf": (cpf, "Este CPF já está cadastrado para outro usuário."),
    }, erros)
    return erros, {"nome": nome, "matricula": matricula, "email": email, "cpf": cpf, "senha": senha}


# ---------------------------------------------------------------- funcionário
def validar_funcionario(dados, conexao, id_funcionario=None):
    erros = {}
    nome = dados.get("nome", "").strip()
    email = dados.get("email", "").strip().lower()
    cpf = somente_digitos(dados.get("cpf"))
    cargo = dados.get("cargo", "").strip()

    _validar_nome(nome, erros)
    _validar_email(email, erros)
    _validar_cpf(cpf, erros)
    if not cargo:
        erros["cargo"] = "Informe o cargo."
    elif not 2 <= len(cargo) <= 50:
        erros["cargo"] = "O cargo deve ter de 2 a 50 caracteres."
    senha = _validar_senha(dados, erros, obrigatoria=id_funcionario is None)

    _checar_unicos(conexao, "funcionario", "id_funcionario", id_funcionario, {
        "email": (email, "Este e-mail já está cadastrado para outro funcionário."),
        "cpf": (cpf, "Este CPF já está cadastrado para outro funcionário."),
    }, erros)
    return erros, {"nome": nome, "email": email, "cpf": cpf, "cargo": cargo, "senha": senha}


# ---------------------------------------------------------------- produto
def validar_produto(dados, arquivo_foto, conexao, id_produto=None):
    erros = {}
    descricao = " ".join(dados.get("descricao", "").split())
    preco = ler_dinheiro(dados.get("preco"))

    if not descricao:
        erros["descricao"] = "Informe a descrição do produto."
    elif not 3 <= len(descricao) <= 150:
        erros["descricao"] = "A descrição deve ter de 3 a 150 caracteres."
    else:
        repetido = conexao.execute(
            "SELECT 1 FROM produto WHERE lower(descricao) = lower(?) AND id_produto != ?",
            (descricao, id_produto or 0)).fetchone()
        if repetido:
            erros["descricao"] = "Já existe um produto com esta descrição."

    if not (dados.get("preco") or "").strip():
        erros["preco"] = "Informe o preço."
    elif preco is None:
        erros["preco"] = "Informe um valor em reais, por exemplo R$ 4,50."
    elif preco <= 0:
        erros["preco"] = "O preço deve ser maior que zero."
    elif preco > PRECO_MAX:
        erros["preco"] = "O preço máximo é R$ 999,99."

    estoque = 0
    if id_produto is None:                  # estoque inicial só no cadastro
        texto = (dados.get("estoque_inicial") or "").strip()
        if texto:
            estoque = ler_inteiro(texto)
            if estoque is None:
                erros["estoque_inicial"] = "Informe um número inteiro, sem vírgula."
            elif estoque > QTD_MAX:
                erros["estoque_inicial"] = f"O máximo é {QTD_MAX} unidades."

    if arquivo_foto and arquivo_foto.filename:
        extensao = os.path.splitext(arquivo_foto.filename)[1].lower()
        arquivo_foto.stream.seek(0, os.SEEK_END)
        tamanho = arquivo_foto.stream.tell()
        arquivo_foto.stream.seek(0)
        if extensao not in EXTENSOES_FOTO:
            erros["foto"] = "Envie uma imagem PNG, JPG ou WEBP."
        elif tamanho > TAMANHO_MAX_FOTO:
            erros["foto"] = "A imagem pode ter até 2 MB."

    return erros, {"descricao": descricao, "preco": preco, "estoque": estoque or 0}


# ---------------------------------------------------------------- estoque e carteira
def validar_entrada_estoque(dados, conexao):
    erros = {}
    id_produto = ler_inteiro(dados.get("id_produto"))
    quantidade = ler_inteiro(dados.get("quantidade"))
    produto = None
    if id_produto is None:
        erros["id_produto"] = "Selecione o produto."
    else:
        produto = conexao.execute("SELECT * FROM produto WHERE id_produto = ? AND ativo = 1",
                                  (id_produto,)).fetchone()
        if produto is None:
            erros["id_produto"] = "Selecione um produto ativo da lista."
    if not (dados.get("quantidade") or "").strip():
        erros["quantidade"] = "Informe a quantidade."
    elif quantidade is None:
        erros["quantidade"] = "Informe um número inteiro, sem vírgula."
    elif quantidade < 1:
        erros["quantidade"] = "A quantidade deve ser de pelo menos 1 unidade."
    elif produto and produto["quantidade_estoque"] + quantidade > QTD_MAX:
        erros["quantidade"] = f"O estoque não pode passar de {QTD_MAX} unidades."
    return erros, {"id_produto": id_produto, "quantidade": quantidade}


def validar_recarga(dados):
    erros = {}
    texto = (dados.get("valor") or "").strip()
    valor = ler_dinheiro(texto)
    if not texto:
        erros["valor"] = "Informe o valor da recarga."
    elif valor is None:
        erros["valor"] = "Informe um valor em reais, por exemplo R$ 10,00."
    elif valor < RECARGA_MIN:
        erros["valor"] = "O valor mínimo da recarga é R$ 1,00."
    elif valor > RECARGA_MAX:
        erros["valor"] = "O valor máximo da recarga é R$ 500,00."
    return erros, {"valor": valor}
