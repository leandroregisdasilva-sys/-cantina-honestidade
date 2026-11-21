-- =============================================================
-- Sistema de Gestão da Cantina da Honestidade - SENAI Friburgo
-- Banco de dados relacional SQLite, conforme o Modelo Entidade e Relacionamento
-- As datas são gravadas pela aplicação no horário local (AAAA-MM-DD HH:MM:SS).
-- =============================================================

PRAGMA foreign_keys = ON;

-- Consumidores (alunos, professores e colaboradores)
CREATE TABLE IF NOT EXISTS usuario (
    id_usuario     INTEGER PRIMARY KEY AUTOINCREMENT,
    nome           VARCHAR(100) NOT NULL,
    matricula      VARCHAR(20)  NOT NULL UNIQUE,
    email          VARCHAR(100) NOT NULL UNIQUE,
    cpf            CHAR(11)     NOT NULL UNIQUE,
    senha          VARCHAR(255) NOT NULL,
    ativo          BOOLEAN      NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1)),
    data_cadastro  DATETIME     NOT NULL
);

-- Funcionários responsáveis pela gestão da cantina
CREATE TABLE IF NOT EXISTS funcionario (
    id_funcionario  INTEGER PRIMARY KEY AUTOINCREMENT,
    nome            VARCHAR(100) NOT NULL,
    cpf             CHAR(11)     NOT NULL UNIQUE,
    email           VARCHAR(100) NOT NULL UNIQUE,
    senha           VARCHAR(255) NOT NULL,
    cargo           VARCHAR(50)  NOT NULL,
    ativo           BOOLEAN      NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1))
);

-- Catálogo de produtos
CREATE TABLE IF NOT EXISTS produto (
    id_produto          INTEGER PRIMARY KEY AUTOINCREMENT,
    id_funcionario      INTEGER        NOT NULL,
    descricao           VARCHAR(150)   NOT NULL,
    preco               DECIMAL(10,2)  NOT NULL CHECK (preco > 0),
    foto_url            VARCHAR(255),
    quantidade_estoque  INTEGER        NOT NULL DEFAULT 0 CHECK (quantidade_estoque >= 0),
    ativo               BOOLEAN        NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1)),
    FOREIGN KEY (id_funcionario) REFERENCES funcionario (id_funcionario)
);

-- Reposições de estoque registradas pelos funcionários
CREATE TABLE IF NOT EXISTS entrada_estoque (
    id_entrada      INTEGER PRIMARY KEY AUTOINCREMENT,
    id_produto      INTEGER  NOT NULL,
    id_funcionario  INTEGER  NOT NULL,
    quantidade      INTEGER  NOT NULL CHECK (quantidade > 0),
    data_hora       DATETIME NOT NULL,
    FOREIGN KEY (id_produto)     REFERENCES produto (id_produto),
    FOREIGN KEY (id_funcionario) REFERENCES funcionario (id_funcionario)
);

-- Cabeçalho de cada compra
CREATE TABLE IF NOT EXISTS venda (
    id_venda     INTEGER PRIMARY KEY AUTOINCREMENT,
    id_usuario   INTEGER       NOT NULL,
    data_hora    DATETIME      NOT NULL,
    valor_total  DECIMAL(10,2) NOT NULL CHECK (valor_total > 0),
    FOREIGN KEY (id_usuario) REFERENCES usuario (id_usuario)
);

-- Itens de cada compra (associativa entre VENDA e PRODUTO)
CREATE TABLE IF NOT EXISTS item_venda (
    id_item         INTEGER PRIMARY KEY AUTOINCREMENT,
    id_venda        INTEGER       NOT NULL,
    id_produto      INTEGER       NOT NULL,
    quantidade      INTEGER       NOT NULL CHECK (quantidade > 0),
    preco_unitario  DECIMAL(10,2) NOT NULL CHECK (preco_unitario > 0),
    FOREIGN KEY (id_venda)   REFERENCES venda (id_venda),
    FOREIGN KEY (id_produto) REFERENCES produto (id_produto)
);

-- Movimentações da carteira virtual. Saldo = créditos - débitos.
-- id_funcionario só é preenchido nas recargas em dinheiro feitas com um funcionário.
CREATE TABLE IF NOT EXISTS transacao_carteira (
    id_transacao    INTEGER PRIMARY KEY AUTOINCREMENT,
    id_usuario      INTEGER       NOT NULL,
    id_funcionario  INTEGER,
    tipo_transacao  VARCHAR(10)   NOT NULL CHECK (tipo_transacao IN ('CREDITO', 'DEBITO')),
    valor           DECIMAL(10,2) NOT NULL CHECK (valor > 0),
    data_hora       DATETIME      NOT NULL,
    FOREIGN KEY (id_usuario)     REFERENCES usuario (id_usuario),
    FOREIGN KEY (id_funcionario) REFERENCES funcionario (id_funcionario)
);

CREATE INDEX IF NOT EXISTS ix_venda_usuario     ON venda (id_usuario);
CREATE INDEX IF NOT EXISTS ix_item_venda_venda  ON item_venda (id_venda);
CREATE INDEX IF NOT EXISTS ix_transacao_usuario ON transacao_carteira (id_usuario);
