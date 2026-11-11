# IndieVault

Um site simples de blogs pra gamers, feito como trabalho da disciplina de Tópicos Especiais em Informática (ADS - Fatec Ribeirão Preto).

A ideia é funcionar parecido com os blogs antigos: cada pessoa cria sua conta, dá um nome pro seu espaço e publica o que quiser (desde texto livre até relatos de jogos zerados, detonados e reviews). Todo mundo dentro da plataforma consegue ler os posts no feed, visitar o blog de outros usuários, curtir publicações e explorar os jogos cadastrados.

**Autor:** Lucas da Silva de Menezes (RA: `2840482313015`)

## O que tem no projeto

- **Blogs pessoais:** cada usuário tem sua própria página (`/blog/<username>`), nome do blog e bio, além de poder editar ou apagar os próprios posts e a própria conta.
- **Posts livres ou ligados a jogos:** dá pra escrever sobre qualquer assunto gamer sem precisar amarrar a um título, ou vincular a algum jogo do catálogo pra colocar nota, horas jogadas e status.
- **Catálogo de jogos e importação da web:** além do cadastro manual, tem uma tela pra importar títulos direto de APIs JSON usando `requests` e `urllib.request`.
- **Backup em `.zip`:** exporta os dados das três tabelas (`usuarios`, `jogos` e `publicacoes`) em arquivos JSON compactados num `.zip`.

## Stack e banco de dados

- **Backend:** Python 3, Flask e Peewee ORM
- **Banco em produção:** PostgreSQL hospedado no **Neon** (lido via `DATABASE_URL`)
- **Hospedagem do site:** **Render** rodando com `gunicorn` (definido no `Procfile`)
- **Desenvolvimento local:** se `DATABASE_URL` não estiver configurada, tenta conectar no PostgreSQL local pelos dados do `.env`; se não tiver nenhum Postgres rodando na máquina, cria e usa o `indievault.db` em SQLite automaticamente.

Quando o banco sobe vazio pela primeira vez, ele já cria alguns jogos e 3 blogs de exemplo (`lucas_menezes`, `rafael_costa` e `marina_souza`, senha `gamer123`), mas também dá pra criar uma conta nova direto em `/cadastro`.

## Rodando na sua máquina

```bash
git clone <url-do-repo>
cd indie_vault

python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
python app.py
```

Depois é só abrir `http://127.0.0.1:5000` no navegador. Se quiser testar conectado direto no Neon localmente, copie o `.env.example` para `.env` e coloque sua `DATABASE_URL`.

## Deploy no Render + Neon

1. Crie o banco PostgreSQL no **Neon** e copie a string de conexão (`postgresql://...?sslmode=require`).
2. No **Render**, crie um Web Service ligado a este repositório em Python 3:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app --workers 2 --threads 4 --bind 0.0.0.0:$PORT`
3. Nas variáveis de ambiente do Render, adicione:
   - `DATABASE_URL`: URL do seu banco no Neon
   - `SECRET_KEY`: uma chave aleatória pra sessão do Flask
