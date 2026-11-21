# Sistema de Gestão da Cantina da Honestidade – SENAI Friburgo

Projeto Aplicado II · Curso Superior de Tecnologia em Análise e Desenvolvimento de Sistemas · UniSENAI
**Equipe 2:** Daniel Paulo Linhares, Gabriel da Silva Marques, Leandro Régis da Silva (líder)
**Orientadora:** Profª Janice Ines Deters

Aplicação web integrada a banco de dados para a Cantina da Honestidade, que funciona em
autoatendimento. O consumidor coloca créditos numa carteira virtual, escolhe os produtos (ou lê o
QR Code da prateleira) e finaliza a compra: o valor sai do saldo e o estoque baixa na hora. O
funcionário da cantina gerencia produtos, estoque, usuários, recargas em dinheiro e relatórios.

---

## 1. Como executar

### Pré-requisito
- **Python 3.10 ou mais novo** ([python.org/downloads](https://www.python.org/downloads/)).
  No Windows, marque **"Add Python to PATH"** na instalação.

### Windows
```bat
cd caminho\da\pasta\cantina-honestidade
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```
Abra **http://127.0.0.1:5000** no navegador.

### macOS / Linux
```bash
cd caminho/da/pasta/cantina-honestidade
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PORT=5001 python app.py
```
Abra **http://127.0.0.1:5001** (no Mac a porta 5000 é usada pelo AirPlay).

Para parar: **Ctrl + C** no terminal. Nas próximas vezes, basta ativar o ambiente (`activate`) e
rodar `python app.py`.

### Banco de dados
Na primeira execução o arquivo **`cantina.db`** (SQLite) é criado sozinho a partir do
`schema.sql`, com dados de exemplo. Para voltar ao estado inicial: pare o sistema, apague o
`cantina.db` e rode de novo.

### Logins de teste

| Perfil | Login | Senha |
|---|---|---|
| Funcionário (painel) | `cantina@senai.br` ou CPF `529.982.247-25` | `admin123` |
| Usuário | matrícula `2026001`, e-mail `ana.souza@aluno.senai.br` ou CPF `111.444.777-35` | `senha123` |
| Usuário | matrícula `2026002` (Carlos) | `senha123` |

CPFs válidos para novos cadastros nos testes: `935.411.347-80`, `153.509.460-56`, `248.438.034-80`.

### Testes automáticos
```bash
python testes.py
```
Roda 11 testes num banco temporário: login, cadastros, validações, compra, saldo insuficiente,
estoque, recargas, relatórios e integridade do banco.

---

## 2. Funcionalidades

| Requisito | Onde | O que faz |
|---|---|---|
| RF01 Cadastro e autenticação | Login, Criar conta, Painel › Usuários | Login por matrícula, e-mail ou CPF; autocadastro; incluir, alterar, consultar, inativar e reativar usuários |
| RF02 Produtos | Painel › Produtos | Incluir, alterar (com foto), consultar, inativar e reativar; QR Codes para imprimir |
| RF03 Carteira virtual | Carteira / Painel › Usuários › Recarga | Recarga online (simulada) ou em dinheiro no balcão, com o funcionário registrado; saldo e extrato |
| RF04 Compra | Produtos, QR Code, Carrinho | Carrinho, conferência de estoque e saldo, desconto automático no saldo e baixa no estoque |
| RF05 Histórico e relatórios | Minhas compras / Painel › Relatórios | Histórico do usuário; vendas, ticket médio, mais vendidos, consumo por usuário e recargas por período |
| RF06 Funcionários | Painel › Funcionários | Incluir, alterar, consultar, inativar e reativar |
| RF07 Estoque | Painel › Estoque | Registro de reposições; alerta de estoque baixo no painel |

**Exclusão lógica:** usuários, funcionários e produtos são **inativados**, não apagados, porque
têm vendas e movimentações ligadas a eles por chave estrangeira. Assim o histórico financeiro
é preservado.

**Compra em transação única:** a venda, os itens, a baixa do estoque e o débito na carteira são
gravados juntos (`BEGIN IMMEDIATE`). Se faltar saldo ou estoque, nada é gravado.

**Saldo calculado:** o saldo não é uma coluna; é a soma dos créditos menos os débitos em
`transacao_carteira`, para nunca divergir do extrato.

---

## 3. Validação dos campos e máscaras

A validação acontece **duas vezes**: no navegador (`static/app.js`), com retorno imediato ao
sair do campo e ao salvar, e no servidor (`validacoes.py`), que confere tudo de novo antes de
gravar, porque a validação do navegador pode ser burlada.

| Campo | Máscara | Regras |
|---|---|---|
| CPF | `000.000.000-00` | Obrigatório; dígitos verificadores; não aceita todos iguais; único |
| Nome | — | Obrigatório; nome e sobrenome; só letras; até 100 caracteres |
| Matrícula | maiúsculas, sem espaços | Obrigatória; 3 a 20 letras ou números; única |
| E-mail | — | Obrigatório; formato `nome@dominio`; único |
| Senha | — | Mínimo 6 caracteres; confirmação igual; gravada com hash |
| Preço | `R$ 0,00` | Obrigatório; número decimal; maior que zero; até R$ 999,99 |
| Recarga | `R$ 0,00` | Obrigatória; de R$ 1,00 a R$ 500,00 |
| Quantidade / estoque | só números | Inteiro; mínimo 1; até 9.999 |
| Foto | — | PNG, JPG ou WEBP; até 2 MB |
| Datas do relatório | calendário | Data válida; final igual ou posterior à inicial |

O banco também protege os dados com `PRIMARY KEY`, `FOREIGN KEY`, `UNIQUE` e `CHECK`
(preço positivo, estoque nunca negativo, tipo de transação só `CREDITO` ou `DEBITO`).

---

## 4. Tecnologias

| Tecnologia | Uso |
|---|---|
| Python 3 | Linguagem do sistema |
| Flask | Framework web: rotas, sessões e telas |
| Jinja2 | Templates HTML (vem com o Flask) |
| Werkzeug | Hash das senhas e upload seguro (vem com o Flask) |
| SQLite + SQL | Banco de dados relacional, arquivo `cantina.db` |
| qrcode | Geração dos QR Codes dos produtos |
| HTML, CSS, JavaScript | Interface, layout responsivo, máscaras e validação no navegador |

Todas são gratuitas (RNF04) e não exigem servidor de banco instalado.

---

## 5. Estrutura

```
cantina-honestidade/
├── app.py            # aplicação Flask: login, cadastro, sair, erros
├── admin.py          # painel do funcionário (usuários, produtos, estoque, relatórios...)
├── loja.py           # autoatendimento (catálogo, carrinho, carteira, compras)
├── servicos.py       # regras de negócio: saldo, recarga e compra
├── validacoes.py     # validação de todos os formulários
├── acesso.py         # controle de acesso por perfil
├── db.py             # conexão com o SQLite e dados de exemplo
├── schema.sql        # criação das 7 tabelas do MER
├── testes.py         # testes automáticos
├── requirements.txt
├── templates/        # telas (auth, admin, loja)
└── static/           # CSS, JavaScript e fotos dos produtos
```

## 6. Modelo de dados

Sete tabelas, conforme o Modelo Entidade e Relacionamento do Documento do Sistema:
`usuario`, `funcionario`, `produto`, `entrada_estoque`, `venda`, `item_venda` e
`transacao_carteira`.
