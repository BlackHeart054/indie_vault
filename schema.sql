CREATE DATABASE indievault_db;

\c indievault_db;

CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    senha_hash VARCHAR(255) NOT NULL,
    nome_completo VARCHAR(100) NOT NULL,
    nome_blog VARCHAR(100) DEFAULT 'Diário Gamer',
    bio VARCHAR(200) DEFAULT 'Compartilhando jogos, ideias e diários de campanha.',
    tipo_usuario VARCHAR(20) DEFAULT 'membro',
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS jogos (
    id SERIAL PRIMARY KEY,
    titulo VARCHAR(150) NOT NULL,
    genero VARCHAR(50) NOT NULL,
    plataforma VARCHAR(50) NOT NULL,
    ano_lancamento INT NOT NULL,
    preco NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    origem_dados VARCHAR(20) DEFAULT 'local',
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS publicacoes (
    id SERIAL PRIMARY KEY,
    usuario_id INT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    jogo_id INT REFERENCES jogos(id) ON DELETE SET NULL,
    titulo VARCHAR(150) NOT NULL,
    categoria VARCHAR(30) DEFAULT 'livre',
    status_jogo VARCHAR(30) DEFAULT 'Postagem Livre',
    horas_jogadas INT DEFAULT 0,
    nota INT CHECK (nota IS NULL OR (nota >= 0 AND nota <= 10)),
    conteudo TEXT NOT NULL,
    votos INT DEFAULT 0,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
