"""Testes automáticos do sistema: rodam com `python testes.py` num banco temporário."""
import io
import os
import re
import tempfile
import unittest

PASTA_TESTE = tempfile.mkdtemp()
os.environ["CANTINA_DB"] = os.path.join(PASTA_TESTE, "teste.db")

from app import app  # noqa: E402  (precisa do CANTINA_DB antes de importar)
from db import conectar  # noqa: E402
from servicos import saldo  # noqa: E402

app.config["TESTING"] = True


def mensagens(resposta):
    html = resposta.get_data(as_text=True)
    return re.findall(r'class="alerta alerta-\w+"[^>]*>(.*?)</div>', html)


def erros_campos(resposta):
    return re.findall(r'class="msg-erro">(.*?)</small>', resposta.get_data(as_text=True))


class TesteCantina(unittest.TestCase):
    def setUp(self):
        self.c = app.test_client()

    def entrar(self, perfil, login, senha):
        return self.c.post("/login", data={"perfil": perfil, "login": login, "senha": senha}, follow_redirects=True)

    # -------------------------------------------------------------- acesso
    def test_01_rotas_protegidas(self):
        self.assertIn("/login", self.c.get("/admin/").headers["Location"])
        self.assertIn("/login", self.c.get("/loja/").headers["Location"])

    def test_02_login(self):
        r = self.entrar("usuario", "2026001", "errada")
        self.assertIn("Login ou senha incorretos.", mensagens(r))
        r = self.entrar("usuario", "", "")
        self.assertEqual(len(erros_campos(r)), 2)
        for login in ("2026001", "ana.souza@aluno.senai.br", "111.444.777-35"):
            c = app.test_client()
            r = c.post("/login", data={"perfil": "usuario", "login": login, "senha": "senha123"}, follow_redirects=True)
            self.assertIn("Olá, Ana!", mensagens(r), login)
        r = self.entrar("funcionario", "cantina@senai.br", "admin123")
        self.assertIn("Olá, Marina!", mensagens(r))
        # usuário não entra no painel e funcionário não entra na loja
        self.assertEqual(self.c.get("/loja/").status_code, 302)

    def test_03_cadastro_validacoes(self):
        r = self.c.post("/cadastro", data=dict(nome="Daniel", cpf="111.111.111-11", matricula="a b",
                                               email="x@", senha="123", confirmar_senha="9"))
        self.assertEqual(r.status_code, 400)
        e = erros_campos(r)
        self.assertTrue(any("sobrenome" in x for x in e))
        self.assertTrue(any("CPF inválido" in x for x in e))
        self.assertTrue(any("e-mail válido" in x for x in e))
        self.assertTrue(any("6 caracteres" in x for x in e))
        r = self.c.post("/cadastro", data=dict(nome="Outro Nome", cpf="11144477735", matricula="2026001",
                                               email="ana.souza@aluno.senai.br", senha="abc123", confirmar_senha="abc123"))
        self.assertEqual(len(erros_campos(r)), 3)                       # CPF, matrícula e e-mail repetidos
        r = self.c.post("/cadastro", data=dict(nome="Daniel Paulo Linhares", cpf="935.411.347-80",
                                               matricula="2579194", email="daniel@aluno.senai.br",
                                               senha="abc123", confirmar_senha="abc123"), follow_redirects=True)
        self.assertIn("Cadastro feito!", mensagens(r)[0])

    # -------------------------------------------------------------- funcionário
    def test_04_produtos(self):
        self.entrar("funcionario", "cantina@senai.br", "admin123")
        r = self.c.post("/admin/produtos/novo", data={"descricao": "a", "preco": "abc", "estoque_inicial": "2,5",
                                                      "foto": (io.BytesIO(b"x"), "virus.exe")},
                        content_type="multipart/form-data")
        e = erros_campos(r)
        self.assertEqual(r.status_code, 400)
        self.assertTrue(any("3 a 150" in x for x in e) and any("reais" in x for x in e)
                        and any("inteiro" in x for x in e) and any("PNG" in x for x in e))
        r = self.c.post("/admin/produtos/novo", data={"descricao": "Bombom", "preco": "R$ 0,00"})
        e = erros_campos(r)
        self.assertTrue(any("Já existe" in x for x in e) and any("maior que zero" in x for x in e))
        with open(os.path.join(app.root_path, "static/uploads/exemplos/wafer.png"), "rb") as arquivo:
            png = arquivo.read()
        r = self.c.post("/admin/produtos/novo", data={"descricao": "Suco de Uva 200ml", "preco": "R$ 1.234,56",
                                                      "estoque_inicial": "8"}, follow_redirects=True)
        self.assertTrue(any("máximo" in x for x in erros_campos(r)))
        r = self.c.post("/admin/produtos/novo", data={"descricao": "Suco de Uva 200ml", "preco": "R$ 5,50",
                                                      "estoque_inicial": "8", "foto": (io.BytesIO(png), "suco.png")},
                        content_type="multipart/form-data", follow_redirects=True)
        self.assertIn("cadastrado com sucesso", mensagens(r)[0])
        with conectar() as cx:
            p = cx.execute("SELECT * FROM produto WHERE descricao = 'Suco de Uva 200ml'").fetchone()
            self.assertEqual((p["preco"], p["quantidade_estoque"]), (5.5, 8))
            self.assertTrue(p["foto_url"].startswith("produto_"))
            self.assertEqual(cx.execute("SELECT quantidade FROM entrada_estoque WHERE id_produto = ?",
                                        (p["id_produto"],)).fetchone()[0], 8)
            os.remove(os.path.join(app.root_path, "static/uploads", p["foto_url"]))
            cx.execute("UPDATE produto SET foto_url = NULL WHERE id_produto = ?", (p["id_produto"],))
        r = self.c.post(f"/admin/produtos/{p['id_produto']}/editar", data={"descricao": "Suco de Uva 200ml", "preco": "6,00"},
                        follow_redirects=True)
        self.assertIn("alterado com sucesso", mensagens(r)[0])
        r = self.c.post(f"/admin/produtos/{p['id_produto']}/inativar", follow_redirects=True)
        self.assertIn("inativado", mensagens(r)[0])
        self.assertEqual(self.c.get("/admin/produtos/qrcodes").status_code, 200)
        self.assertIn("<svg", self.c.get("/admin/produtos/qrcodes").get_data(as_text=True))

    def test_05_estoque_e_funcionarios(self):
        self.entrar("funcionario", "cantina@senai.br", "admin123")
        r = self.c.post("/admin/estoque", data={"id_produto": "", "quantidade": "0"})
        self.assertEqual(len(erros_campos(r)), 2)
        r = self.c.post("/admin/estoque", data={"id_produto": "6", "quantidade": "10"}, follow_redirects=True)
        self.assertIn("Estoque atual: 14", mensagens(r)[0])
        r = self.c.post("/admin/funcionarios/novo", data=dict(nome="João Silva", cpf="15350946056", cargo="Atendente",
                                                             email="joao@senai.br", senha="abc123", confirmar_senha="abc123"),
                        follow_redirects=True)
        self.assertIn("cadastrado com sucesso", mensagens(r)[0])
        r = self.c.post("/admin/funcionarios/1/inativar", follow_redirects=True)
        self.assertIn("próprio cadastro", mensagens(r)[0])
        r = self.c.post("/admin/funcionarios/2/inativar", follow_redirects=True)
        self.assertIn("inativado", mensagens(r)[0])

    def test_06_recarga_balcao(self):
        self.entrar("funcionario", "cantina@senai.br", "admin123")
        r = self.c.post("/admin/usuarios/3/recarga", data={"valor": "R$ 0,50"})
        self.assertTrue(any("mínimo" in x for x in erros_campos(r)))
        r = self.c.post("/admin/usuarios/3/recarga", data={"valor": "R$ 600,00"})
        self.assertTrue(any("máximo" in x for x in erros_campos(r)))
        r = self.c.post("/admin/usuarios/3/recarga", data={"valor": "R$ 10,00"}, follow_redirects=True)
        self.assertIn("R$ 10,00", mensagens(r)[0])
        with conectar() as cx:
            t = cx.execute("SELECT * FROM transacao_carteira WHERE id_usuario = 3").fetchone()
            self.assertEqual(t["id_funcionario"], 1)

    # -------------------------------------------------------------- consumidor
    def test_07_compra(self):
        self.entrar("usuario", "2026002", "senha123")              # Carlos: saldo R$ 15,00
        r = self.c.post("/loja/carrinho/adicionar/1", data={"quantidade": "999"}, follow_redirects=True)
        self.assertIn("Só é possível levar", mensagens(r)[0])
        self.c.post("/loja/carrinho/adicionar/1", data={"quantidade": "2"})    # 2 × 6,00
        self.c.post("/loja/carrinho/adicionar/4", data={"quantidade": "1"})    # 1 × 4,50 = 16,50 > 15
        r = self.c.get("/loja/carrinho")
        self.assertIn("Faltam R$ 1,50", r.get_data(as_text=True))
        r = self.c.post("/loja/carrinho/finalizar", follow_redirects=True)
        self.assertIn("Saldo insuficiente", mensagens(r)[0])
        with conectar() as cx:
            estoque_antes = cx.execute("SELECT quantidade_estoque FROM produto WHERE id_produto = 1").fetchone()[0]
        self.c.post("/loja/carrinho/alterar/4", data={"quantidade": "0"})
        r = self.c.post("/loja/carrinho/finalizar", follow_redirects=True)
        self.assertTrue(any("R$ 12,00 descontados" in m for m in mensagens(r)), mensagens(r))
        with conectar() as cx:
            self.assertEqual(saldo(cx, 2), 3)
            self.assertEqual(cx.execute("SELECT quantidade_estoque FROM produto WHERE id_produto = 1").fetchone()[0],
                             estoque_antes - 2)
        r = self.c.get("/loja/compras")
        self.assertIn("2 × Batata Chips Original 45g", r.get_data(as_text=True))

    def test_08_carteira_online(self):
        self.entrar("usuario", "2026002", "senha123")
        r = self.c.post("/loja/carteira", data={"valor": ""})
        self.assertTrue(any("Informe o valor" in x for x in erros_campos(r)))
        r = self.c.post("/loja/carteira", data={"valor": "R$ 20,00"}, follow_redirects=True)
        self.assertIn("Recarga de R$ 20,00 confirmada.", mensagens(r))
        self.assertIn("Recarga online", r.get_data(as_text=True))

    def test_09_relatorios_e_painel(self):
        self.entrar("funcionario", "cantina@senai.br", "admin123")
        self.assertEqual(self.c.get("/admin/").status_code, 200)
        r = self.c.get("/admin/relatorios?de=2020-01-01&ate=2030-12-31")
        html = r.get_data(as_text=True)
        self.assertIn("Batata Chips Original 45g", html)
        r = self.c.get("/admin/relatorios?de=2030-01-01&ate=2020-01-01")
        self.assertIn("posterior", r.get_data(as_text=True))
        r = self.c.get("/admin/relatorios?de=abc")
        self.assertIn("inválida", r.get_data(as_text=True))

    def test_10_integridade_do_banco(self):
        import sqlite3
        with conectar() as cx:
            with self.assertRaises(sqlite3.IntegrityError):
                cx.execute("INSERT INTO venda (id_usuario, data_hora, valor_total) VALUES (999, '2026-01-01 00:00:00', 5)")
            with self.assertRaises(sqlite3.IntegrityError):
                cx.execute("UPDATE produto SET quantidade_estoque = -1 WHERE id_produto = 1")
            senha = cx.execute("SELECT senha FROM usuario WHERE id_usuario = 1").fetchone()[0]
            self.assertNotIn("senha123", senha)

    def test_11_todas_as_telas_abrem(self):
        self.entrar("funcionario", "cantina@senai.br", "admin123")
        for url in ["/admin/", "/admin/usuarios", "/admin/usuarios/novo", "/admin/usuarios/1/editar",
                    "/admin/usuarios/1/recarga", "/admin/funcionarios", "/admin/funcionarios/novo",
                    "/admin/funcionarios/1/editar", "/admin/produtos", "/admin/produtos/novo",
                    "/admin/produtos/1/editar", "/admin/estoque", "/admin/relatorios", "/admin/produtos/qrcodes"]:
            self.assertEqual(self.c.get(url).status_code, 200, url)
        self.assertEqual(self.c.get("/admin/usuarios/999/editar").status_code, 404)
        c = app.test_client()
        c.post("/login", data={"perfil": "usuario", "login": "2026001", "senha": "senha123"})
        for url in ["/loja/", "/loja/produto/1", "/loja/carrinho", "/loja/carteira", "/loja/compras"]:
            self.assertEqual(c.get(url).status_code, 200, url)


if __name__ == "__main__":
    unittest.main(verbosity=2)
