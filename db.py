"""Conexão com o banco SQLite, criação das tabelas e dados de exemplo."""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

PASTA = os.path.dirname(os.path.abspath(__file__))
CAMINHO_BANCO = os.environ.get("CANTINA_DB", os.path.join(PASTA, "cantina.db"))
CAMINHO_SCHEMA = os.path.join(PASTA, "schema.sql")


def agora(delta_dias=0, hora=None):
    """Data e hora local no formato gravado no banco."""
    momento = datetime.now() + timedelta(days=delta_dias)
    if hora:
        momento = momento.replace(hour=hora[0], minute=hora[1], second=0)
    return momento.strftime("%Y-%m-%d %H:%M:%S")


@contextmanager
def conectar():
    """Abre a conexão, confirma (commit) se tudo deu certo, desfaz (rollback) se deu erro e sempre fecha."""
    conexao = sqlite3.connect(CAMINHO_BANCO, timeout=10)
    conexao.row_factory = sqlite3.Row            # acessar as colunas pelo nome
    conexao.execute("PRAGMA foreign_keys = ON")  # o SQLite só aplica as FKs com isto ligado
    try:
        yield conexao
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise
    finally:
        conexao.close()


def inicializar_banco():
    """Cria as tabelas (se não existirem) e insere dados de exemplo na primeira execução."""
    banco_novo = not os.path.exists(CAMINHO_BANCO)
    with conectar() as conexao:
        with open(CAMINHO_SCHEMA, encoding="utf-8") as arquivo:
            conexao.executescript(arquivo.read())
        if banco_novo:
            _inserir_dados_exemplo(conexao)


def _inserir_dados_exemplo(cx):
    # Funcionário responsável pela cantina
    cx.execute(
        "INSERT INTO funcionario (nome, cpf, email, senha, cargo) VALUES (?, ?, ?, ?, ?)",
        ("Marina Costa", "52998224725", "cantina@senai.br",
         generate_password_hash("admin123"), "Gestora da cantina"),
    )

    # Usuários (consumidores)
    usuarios = [
        ("Ana Beatriz Souza", "2026001", "ana.souza@aluno.senai.br", "11144477735"),
        ("Carlos Eduardo Lima", "2026002", "carlos.lima@aluno.senai.br", "39053344705"),
        ("Fernanda Rocha", "PROF015", "fernanda.rocha@senai.br", "71428793860"),
    ]
    for nome, matricula, email, cpf in usuarios:
        cx.execute(
            "INSERT INTO usuario (nome, matricula, email, cpf, senha, data_cadastro) VALUES (?, ?, ?, ?, ?, ?)",
            (nome, matricula, email, cpf, generate_password_hash("senha123"), agora(-20)),
        )

    # Produtos da cantina, com foto de exemplo e estoque inicial registrado como entrada
    produtos = [
        ("Batata Chips Original 45g", 6.00, "exemplos/batata-chips.png", 20),
        ("Batata Ondulada Cebola e Salsa 45g", 6.00, "exemplos/batata-ondulada.png", 15),
        ("Bala de Gelatina Fini 90g", 5.00, "exemplos/bala-fini.png", 12),
        ("Wafer de Chocolate 100g", 4.50, "exemplos/wafer.png", 10),
        ("Bombom", 2.00, "exemplos/bombom.png", 40),
        ("Paçoca", 1.50, "exemplos/pacoca.png", 4),
    ]
    for descricao, preco, foto, estoque in produtos:
        cur = cx.execute(
            "INSERT INTO produto (id_funcionario, descricao, preco, foto_url, quantidade_estoque) VALUES (1, ?, ?, ?, ?)",
            (descricao, preco, foto, estoque),
        )
        cx.execute(
            "INSERT INTO entrada_estoque (id_produto, id_funcionario, quantidade, data_hora) VALUES (?, 1, ?, ?)",
            (cur.lastrowid, estoque, agora(-15, (8, 0))),
        )

    # Movimentações de exemplo: recargas e uma compra da Ana
    cx.execute("INSERT INTO transacao_carteira (id_usuario, id_funcionario, tipo_transacao, valor, data_hora) "
               "VALUES (1, 1, 'CREDITO', 20.00, ?)", (agora(-3, (9, 10)),))
    cx.execute("INSERT INTO transacao_carteira (id_usuario, id_funcionario, tipo_transacao, valor, data_hora) "
               "VALUES (2, NULL, 'CREDITO', 15.00, ?)", (agora(-2, (13, 5)),))
    venda = cx.execute("INSERT INTO venda (id_usuario, data_hora, valor_total) VALUES (1, ?, 8.00)",
                       (agora(-1, (10, 15)),)).lastrowid
    cx.execute("INSERT INTO item_venda (id_venda, id_produto, quantidade, preco_unitario) VALUES (?, 1, 1, 6.00)", (venda,))
    cx.execute("INSERT INTO item_venda (id_venda, id_produto, quantidade, preco_unitario) VALUES (?, 5, 1, 2.00)", (venda,))
    cx.execute("UPDATE produto SET quantidade_estoque = quantidade_estoque - 1 WHERE id_produto IN (1, 5)")
    cx.execute("INSERT INTO transacao_carteira (id_usuario, id_funcionario, tipo_transacao, valor, data_hora) "
               "VALUES (1, NULL, 'DEBITO', 8.00, ?)", (agora(-1, (10, 15)),))
