"""Regras de negócio que envolvem mais de uma tabela: saldo da carteira, compra e recarga."""
from decimal import Decimal

from db import agora


class ErroNegocio(Exception):
    """Regra de negócio não atendida (saldo insuficiente, estoque acabou...)."""


def saldo(conexao, id_usuario):
    """O saldo não fica gravado: é a soma dos créditos menos a soma dos débitos."""
    linha = conexao.execute(
        """SELECT COALESCE(SUM(CASE WHEN tipo_transacao = 'CREDITO' THEN valor ELSE -valor END), 0)
           FROM transacao_carteira WHERE id_usuario = ?""",
        (id_usuario,),
    ).fetchone()
    return Decimal(str(linha[0])).quantize(Decimal("0.01"))


def registrar_recarga(conexao, id_usuario, valor, id_funcionario=None):
    conexao.execute(
        """INSERT INTO transacao_carteira (id_usuario, id_funcionario, tipo_transacao, valor, data_hora)
           VALUES (?, ?, 'CREDITO', ?, ?)""",
        (id_usuario, id_funcionario, float(valor), agora()),
    )


def registrar_compra(conexao, id_usuario, carrinho):
    """Grava a venda inteira numa única transação do banco.

    carrinho: {id_produto: quantidade}. Confere produto ativo, estoque e saldo; grava VENDA,
    ITEM_VENDA, baixa o estoque e lança o DÉBITO. Se algo falhar, nada é gravado.
    """
    if not carrinho:
        raise ErroNegocio("O carrinho está vazio.")

    conexao.execute("BEGIN IMMEDIATE")        # trava a escrita até o fim da compra
    try:
        itens, total = [], Decimal("0.00")
        for id_produto, quantidade in carrinho.items():
            produto = conexao.execute(
                "SELECT * FROM produto WHERE id_produto = ?", (id_produto,)).fetchone()
            if produto is None or not produto["ativo"]:
                raise ErroNegocio("Um produto do carrinho não está mais disponível. Remova-o e tente de novo.")
            if quantidade > produto["quantidade_estoque"]:
                raise ErroNegocio(
                    f"Só há {produto['quantidade_estoque']} unidade(s) de {produto['descricao']} no estoque.")
            preco = Decimal(str(produto["preco"])).quantize(Decimal("0.01"))
            itens.append((produto, quantidade, preco))
            total += preco * quantidade

        disponivel = saldo(conexao, id_usuario)
        if total > disponivel:
            raise ErroNegocio(
                f"Saldo insuficiente: a compra custa R$ {total:.2f} e seu saldo é R$ {disponivel:.2f}."
                .replace(".", ","))

        momento = agora()
        id_venda = conexao.execute(
            "INSERT INTO venda (id_usuario, data_hora, valor_total) VALUES (?, ?, ?)",
            (id_usuario, momento, float(total))).lastrowid
        for produto, quantidade, preco in itens:
            conexao.execute(
                "INSERT INTO item_venda (id_venda, id_produto, quantidade, preco_unitario) VALUES (?, ?, ?, ?)",
                (id_venda, produto["id_produto"], quantidade, float(preco)))
            conexao.execute(
                "UPDATE produto SET quantidade_estoque = quantidade_estoque - ? WHERE id_produto = ?",
                (quantidade, produto["id_produto"]))
        conexao.execute(
            """INSERT INTO transacao_carteira (id_usuario, id_funcionario, tipo_transacao, valor, data_hora)
               VALUES (?, NULL, 'DEBITO', ?, ?)""",
            (id_usuario, float(total), momento))
        conexao.commit()
        return id_venda, total
    except Exception:
        conexao.rollback()
        raise
