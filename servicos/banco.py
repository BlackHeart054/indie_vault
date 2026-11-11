import os
from datetime import datetime
from functools import reduce
import operator
import psycopg2
from psycopg2 import sql
from peewee import (
    DatabaseProxy, PostgresqlDatabase, SqliteDatabase, Model,
    CharField, IntegerField, DecimalField, TextField, DateTimeField,
    ForeignKeyField, AutoField, fn, JOIN, SQL, Check
)
from playhouse.shortcuts import model_to_dict
from playhouse.db_url import connect as conectar_url_db
from werkzeug.security import generate_password_hash, check_password_hash
from config import Config

banco_dados = DatabaseProxy()
MOTOR_ATIVO = "PostgreSQL"

DIRETORIO_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAMINHO_SQLITE = os.path.join(DIRETORIO_BASE, 'indievault.db')

CATEGORIAS_VALIDAS = ('livre', 'zerado', 'detonado', 'experiencia', 'analise')


def configurar_postgres():
    return PostgresqlDatabase(
        Config.DB_NAME,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        host=Config.DB_HOST,
        port=int(Config.DB_PORT),
        connect_timeout=3
    )


def configurar_sqlite():
    return SqliteDatabase(
        CAMINHO_SQLITE,
        pragmas={'foreign_keys': 1, 'journal_mode': 'wal'}
    )


banco_dados.initialize(configurar_postgres())


class ModeloBase(Model):
    class Meta:
        database = banco_dados

    def __getitem__(self, item):
        if hasattr(self, item):
            return getattr(self, item)
        raise KeyError(item)

    def para_dicionario(self):
        return model_to_dict(self)


class Usuario(ModeloBase):
    id = AutoField()
    username = CharField(max_length=50, unique=True)
    senha_hash = CharField(max_length=255)
    nome_completo = CharField(max_length=100)
    nome_blog = CharField(max_length=100, default='Diário Gamer')
    bio = CharField(max_length=200, default='Jogando e escrevendo no meu cantinho.')
    tipo_usuario = CharField(max_length=20, default='membro')
    criado_em = DateTimeField(default=datetime.now)

    class Meta:
        table_name = 'usuarios'


class Jogo(ModeloBase):
    id = AutoField()
    titulo = CharField(max_length=150)
    genero = CharField(max_length=50)
    plataforma = CharField(max_length=50)
    ano_lancamento = IntegerField()
    preco = DecimalField(max_digits=10, decimal_places=2, default=0.00)
    origem_dados = CharField(max_length=20, default='local')
    criado_em = DateTimeField(default=datetime.now)

    class Meta:
        table_name = 'jogos'


class Publicacao(ModeloBase):
    id = AutoField()
    usuario = ForeignKeyField(Usuario, backref='publicacoes', on_delete='CASCADE', column_name='usuario_id')
    jogo = ForeignKeyField(Jogo, backref='publicacoes', on_delete='SET NULL', null=True, column_name='jogo_id')
    titulo = CharField(max_length=150)
    categoria = CharField(max_length=30, default='livre')
    status_jogo = CharField(max_length=30, default='Postagem Livre')
    horas_jogadas = IntegerField(default=0)
    nota = IntegerField(null=True, constraints=[Check('nota IS NULL OR (nota >= 0 AND nota <= 10)')])
    conteudo = TextField()
    votos = IntegerField(default=0)
    criado_em = DateTimeField(default=datetime.now)

    class Meta:
        table_name = 'publicacoes'


def criar_banco_postgres_se_nao_existir():
    conexao = psycopg2.connect(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        dbname='postgres',
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        connect_timeout=3
    )
    conexao.autocommit = True
    with conexao.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (Config.DB_NAME,))
        if not cursor.fetchone():
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(Config.DB_NAME)))
    conexao.close()


def _garantir_migracao_sqlite_publicacoes():
    """Torna jogo_id e nota opcionais no SQLite caso o banco tenha sido criado no esquema antigo."""
    colunas = banco_dados.execute_sql("PRAGMA table_info(publicacoes);").fetchall()
    info = {col[1]: col for col in colunas}
    jogo_notnull = info.get('jogo_id', (None, None, None, 0))[3] == 1
    if not jogo_notnull:
        return

    banco_dados.execute_sql("PRAGMA foreign_keys=OFF;")
    with banco_dados.atomic():
        banco_dados.execute_sql("""
            CREATE TABLE publicacoes_migrada (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                jogo_id INTEGER REFERENCES jogos(id) ON DELETE SET NULL,
                titulo VARCHAR(150) NOT NULL,
                categoria VARCHAR(30) DEFAULT 'livre',
                status_jogo VARCHAR(30) DEFAULT 'Postagem Livre',
                horas_jogadas INTEGER DEFAULT 0,
                nota INTEGER CHECK (nota IS NULL OR (nota >= 0 AND nota <= 10)),
                conteudo TEXT NOT NULL,
                votos INTEGER DEFAULT 0,
                criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        banco_dados.execute_sql("""
            INSERT INTO publicacoes_migrada (
                id, usuario_id, jogo_id, titulo, categoria, status_jogo,
                horas_jogadas, nota, conteudo, votos, criado_em
            )
            SELECT
                id, usuario_id, jogo_id, titulo, categoria, status_jogo,
                horas_jogadas, nota, conteudo, votos, criado_em
            FROM publicacoes;
        """)
        banco_dados.execute_sql("DROP TABLE publicacoes;")
        banco_dados.execute_sql("ALTER TABLE publicacoes_migrada RENAME TO publicacoes;")
    banco_dados.execute_sql("PRAGMA foreign_keys=ON;")


def _garantir_colunas_extras():
    colunas_usuario = {c.name for c in banco_dados.get_columns('usuarios')}
    if 'bio' not in colunas_usuario:
        try:
            banco_dados.execute_sql(
                "ALTER TABLE usuarios ADD COLUMN bio VARCHAR(200) DEFAULT 'Compartilhando jogos, ideias e diários de campanha.';"
            )
        except Exception:
            pass
    if 'nome_blog' not in colunas_usuario:
        try:
            banco_dados.execute_sql(
                "ALTER TABLE usuarios ADD COLUMN nome_blog VARCHAR(100) DEFAULT 'Diário Gamer';"
            )
        except Exception:
            pass

    if isinstance(banco_dados.obj, SqliteDatabase):
        try:
            _garantir_migracao_sqlite_publicacoes()
        except Exception:
            pass
    else:
        for comando in (
            "ALTER TABLE publicacoes ALTER COLUMN jogo_id DROP NOT NULL;",
            "ALTER TABLE publicacoes ALTER COLUMN nota DROP NOT NULL;",
        ):
            try:
                banco_dados.execute_sql(comando)
            except Exception:
                pass

    # Normaliza contas antigas de protótipo sem distinção admin/comum
    try:
        Usuario.update(tipo_usuario='membro').where(Usuario.tipo_usuario != 'membro').execute()
        legado_admin = Usuario.get_or_none(Usuario.username == 'admin')
        if legado_admin and not Usuario.get_or_none(Usuario.username == 'lucas_menezes'):
            legado_admin.username = 'lucas_menezes'
            legado_admin.nome_completo = 'Lucas Menezes'
            legado_admin.nome_blog = 'Caderno do Lucas'
            legado_admin.tipo_usuario = 'membro'
            legado_admin.save()

        lucas_seed = Usuario.get_or_none(Usuario.username == 'lucas_menezes')
        if lucas_seed and lucas_seed.bio == 'Gamer na comunidade IndieVault':
            lucas_seed.bio = 'Curto metroidvania, survival horror e uns RPGs no PC e Switch.'
            lucas_seed.save()

        Publicacao.update(
            titulo='Zerei o Capítulo 9 (Farewell) sem Assist Mode: quase perdi a sanidade'
        ).where(
            Publicacao.titulo == 'Zerei o Capítulo 9 (Farewell) sem Assist Mode — que experiência inesquecível'
        ).execute()
    except Exception:
        pass


def obter_motor_ativo():
    return MOTOR_ATIVO


def popular_dados_iniciais():
    if Usuario.select().count() == 0:
        Usuario.create(
            username='lucas_menezes',
            senha_hash=generate_password_hash('gamer123'),
            nome_completo='Lucas Menezes',
            nome_blog='Caderno do Lucas',
            bio='Curto metroidvania, survival horror e uns RPGs no PC e Switch.',
            tipo_usuario='membro'
        )
        Usuario.create(
            username='rafael_costa',
            senha_hash=generate_password_hash('gamer123'),
            nome_completo='Rafael Costa',
            nome_blog='Diário de Bosses',
            bio='Sofrendo em chefe difícil e tentando pegar 100% nas platinas.',
            tipo_usuario='membro'
        )
        Usuario.create(
            username='marina_souza',
            senha_hash=generate_password_hash('gamer123'),
            nome_completo='Marina Souza',
            nome_blog='Pixels & Café',
            bio='Fã de jogo de plataforma, pixel art e trilha sonora boa.',
            tipo_usuario='membro'
        )

    if Jogo.select().count() == 0:
        jogos_iniciais = [
            {'titulo': 'Hollow Knight', 'genero': 'Metroidvania', 'plataforma': 'PC / Switch / PS4', 'ano_lancamento': 2017, 'preco': 46.99, 'origem_dados': 'local'},
            {'titulo': 'Signalis', 'genero': 'Survival Horror', 'plataforma': 'PC / PS4 / Switch', 'ano_lancamento': 2022, 'preco': 59.90, 'origem_dados': 'local'},
            {'titulo': 'Celeste', 'genero': 'Plataforma', 'plataforma': 'PC / Switch / PS4 / Xbox', 'ano_lancamento': 2018, 'preco': 36.99, 'origem_dados': 'local'},
            {'titulo': 'Stardew Valley', 'genero': 'Simulação / RPG', 'plataforma': 'PC / Switch / Mobile', 'ano_lancamento': 2016, 'preco': 24.99, 'origem_dados': 'local'},
            {'titulo': 'Undertale', 'genero': 'RPG', 'plataforma': 'PC / Switch / PS4', 'ano_lancamento': 2015, 'preco': 19.99, 'origem_dados': 'local'},
            {'titulo': 'Disco Elysium', 'genero': 'RPG Narrativo', 'plataforma': 'PC / PS5 / Switch', 'ano_lancamento': 2019, 'preco': 75.49, 'origem_dados': 'local'}
        ]
        for jogo in jogos_iniciais:
            Jogo.create(**jogo)

    if Publicacao.select().count() == 0:
        u_lucas = Usuario.get_or_none(Usuario.username == 'lucas_menezes') or Usuario.select().first()
        u_rafael = Usuario.get_or_none(Usuario.username == 'rafael_costa') or u_lucas
        u_marina = Usuario.get_or_none(Usuario.username == 'marina_souza') or u_lucas

        j_signalis = Jogo.get_or_none(Jogo.titulo == 'Signalis')
        j_hk = Jogo.get_or_none(Jogo.titulo == 'Hollow Knight')
        j_celeste = Jogo.get_or_none(Jogo.titulo == 'Celeste')
        j_disco = Jogo.get_or_none(Jogo.titulo == 'Disco Elysium')

        if u_lucas and j_signalis:
            Publicacao.create(
                usuario=u_lucas,
                jogo=j_signalis,
                titulo='Detonado rápido: cofre do 2º andar e como pegar o Final da Promessa',
                categoria='detonado',
                status_jogo='Platinado (100%)',
                horas_jogadas=18,
                nota=10,
                votos=24,
                conteudo=(
                    'Pra quem travou no cofre do 2º andar de Sierpinski: abre o rádio no inventário e '
                    'sintoniza em 140.00 MHz pra pegar os números da estação Eusan.\n\n'
                    'Já pro final "Promessa", a dica é ir pra cima mesmo: não fique evitando combate nos corredores, '
                    'tome dano sem sair curando toda hora, fale com todos os NPCs e tente abrir as portas trancadas. '
                    'O jogo vai anotando tudo escondido e decide seu final no fim da run.'
                )
            )

        if u_rafael and j_hk:
            Publicacao.create(
                usuario=u_rafael,
                jogo=j_hk,
                titulo='Finalmente 112% no Hollow Knight! Build pra passar do 5º Panteão',
                categoria='zerado',
                status_jogo='Platinado (100%)',
                horas_jogadas=85,
                nota=10,
                votos=38,
                conteudo=(
                    'Depois de 85 horas sofrendo na Radiância Absoluta, finalmente deu bom! '
                    'Se alguém tiver travado no final de Hallownest, essa build salvou demais:\n'
                    '- Força Inquebrável\n'
                    '- Corte Rápido\n'
                    '- Pedra do Xamã\n'
                    '- Apanhador de Almas\n\n'
                    'A manha é guardar alma na fase das plataformas pra espamar Grito do Abismo assim que ela subir.'
                )
            )

        if u_marina and j_celeste:
            Publicacao.create(
                usuario=u_marina,
                jogo=j_celeste,
                titulo='Zerei o Capítulo 9 (Farewell) sem Assist Mode: quase perdi a sanidade',
                categoria='experiencia',
                status_jogo='Zerado (História)',
                horas_jogadas=34,
                nota=10,
                votos=31,
                conteudo=(
                    'Foram mais de 3.200 mortes só no Farewell, mas acertar aquela última sequência de wavedash dá '
                    'uma sensação absurda. O jeito que o jogo mistura ansiedade e superação na gameplay sem virar '
                    'palestra faz Celeste ser especial demais.'
                )
            )

        if u_lucas:
            Publicacao.create(
                usuario=u_lucas,
                jogo=None,
                titulo='Saudade da época de escrever sobre jogos em blog',
                categoria='livre',
                status_jogo='Postagem Livre',
                horas_jogadas=0,
                nota=None,
                votos=19,
                conteudo=(
                    'Durante muito tempo eu só saía correndo de um jogo pro outro tentando zerar o backlog, e no mês '
                    'seguinte nem lembrava direito do que tinha jogado.\n\n'
                    'Começar a anotar o que eu achei de cada campanha, boss chato e umas dicas soltas mudou tudo, '
                    'bem naquela pegada dos blogs antigos de madrugada. Muito bom poder ler os relatos da galera por aqui também.'
                )
            )

        if u_marina and j_disco:
            Publicacao.create(
                usuario=u_marina,
                jogo=j_disco,
                titulo='Disco Elysium tem os melhores diálogos que já vi num RPG',
                categoria='analise',
                status_jogo='Zerado (História)',
                horas_jogadas=40,
                nota=9,
                votos=17,
                conteudo=(
                    'Mesmo sem combate tradicional, cada rolagem de dado com as vozes da cabeça do detetive parece '
                    'uma luta de boss. Se você vai começar agora, bota pontos em "Império Interior" e "Enciclopédia" '
                    'que o jogo fica mil vezes mais engraçado e viajado.'
                )
            )


def inicializar_banco():
    global MOTOR_ATIVO

    if Config.DATABASE_URL:
        try:
            url_banco = Config.DATABASE_URL
            if url_banco.startswith('postgres://'):
                url_banco = 'postgresql://' + url_banco[len('postgres://'):]
            db_nuvem = conectar_url_db(url_banco)
            banco_dados.initialize(db_nuvem)
            banco_dados.connect(reuse_if_open=True)
            banco_dados.create_tables([Usuario, Jogo, Publicacao], safe=True)
            _garantir_colunas_extras()
            popular_dados_iniciais()
            MOTOR_ATIVO = "PostgreSQL (Nuvem)"
            return True, "PostgreSQL na nuvem inicializado com sucesso."
        except Exception:
            pass

    try:
        criar_banco_postgres_se_nao_existir()
        pg_db = configurar_postgres()
        banco_dados.initialize(pg_db)
        banco_dados.connect(reuse_if_open=True)
        banco_dados.create_tables([Usuario, Jogo, Publicacao], safe=True)
        _garantir_colunas_extras()
        popular_dados_iniciais()
        MOTOR_ATIVO = f"PostgreSQL ({Config.DB_NAME})"
        return True, f"PostgreSQL ({Config.DB_NAME}) inicializado com sucesso."
    except Exception:
        pass

    try:
        sqlite_db = configurar_sqlite()
        banco_dados.initialize(sqlite_db)
        banco_dados.connect(reuse_if_open=True)
        banco_dados.create_tables([Usuario, Jogo, Publicacao], safe=True)
        _garantir_colunas_extras()
        popular_dados_iniciais()
        MOTOR_ATIVO = "SQLite (indievault.db)"
        return True, "Banco local SQLite (indievault.db) inicializado com sucesso."
    except Exception as erro:
        return False, f"Erro ao inicializar banco de dados: {erro}"


# Operações da Tabela 1: usuarios

def autenticar_usuario(username, senha):
    usuario = Usuario.get_or_none(fn.LOWER(Usuario.username) == username.strip().lower())
    if usuario and check_password_hash(usuario.senha_hash, senha):
        return usuario
    return None


def obter_usuario_por_id(usuario_id):
    return Usuario.get_or_none(Usuario.id == usuario_id)


def obter_usuario_por_username(username):
    return Usuario.get_or_none(fn.LOWER(Usuario.username) == username.strip().lower())


def criar_usuario(username, senha, nome_completo, bio='', nome_blog=''):
    senha_hash = generate_password_hash(senha)
    nome_limpo = nome_completo.strip()
    primeiro_nome = nome_limpo.split()[0] if nome_limpo else username.strip()
    blog_limpo = (nome_blog or '').strip() or f'Blog de {primeiro_nome}'
    bio_limpa = (bio or '').strip() or 'Jogando e escrevendo no meu cantinho.'
    return Usuario.create(
        username=username.strip().lower(),
        senha_hash=senha_hash,
        nome_completo=nome_limpo,
        nome_blog=blog_limpo[:100],
        bio=bio_limpa[:200],
        tipo_usuario='membro'
    )


def atualizar_usuario(usuario_id, username, nome_completo, bio='', nome_blog='', nova_senha=None):
    usuario = Usuario.get_or_none(Usuario.id == usuario_id)
    if not usuario:
        return None
    nome_limpo = nome_completo.strip()
    primeiro_nome = nome_limpo.split()[0] if nome_limpo else username.strip()
    usuario.username = username.strip().lower()
    usuario.nome_completo = nome_limpo
    usuario.nome_blog = ((nome_blog or '').strip() or f'Blog de {primeiro_nome}')[:100]
    usuario.bio = ((bio or '').strip() or 'Jogando e escrevendo no meu cantinho.')[:200]
    if nova_senha and len(nova_senha.strip()) >= 4:
        usuario.senha_hash = generate_password_hash(nova_senha.strip())
    usuario.save()
    return usuario


def listar_usuarios():
    consulta = (
        Usuario.select(
            Usuario,
            fn.COUNT(Publicacao.id).alias('total_publicacoes'),
            fn.COALESCE(fn.SUM(Publicacao.votos), 0).alias('total_curtidas')
        )
        .join(Publicacao, JOIN.LEFT_OUTER, on=(Publicacao.usuario == Usuario.id))
        .group_by(Usuario.id)
        .order_by(SQL('total_publicacoes').desc(), Usuario.id.asc())
    )
    return list(consulta)


def listar_blogs(busca='', limite=None):
    consulta = (
        Usuario.select(
            Usuario,
            fn.COUNT(Publicacao.id).alias('total_publicacoes'),
            fn.COALESCE(fn.SUM(Publicacao.votos), 0).alias('total_curtidas')
        )
        .join(Publicacao, JOIN.LEFT_OUTER, on=(Publicacao.usuario == Usuario.id))
        .group_by(Usuario.id)
    )
    if busca:
        termo = f"%{busca.strip()}%"
        consulta = consulta.where(
            (Usuario.username.ilike(termo))
            | (Usuario.nome_completo.ilike(termo))
            | (Usuario.nome_blog.ilike(termo))
            | (Usuario.bio.ilike(termo))
        )

    consulta = consulta.order_by(SQL('total_publicacoes').desc(), Usuario.id.asc())
    if limite:
        consulta = consulta.limit(int(limite))

    blogs = list(consulta)
    for b in blogs:
        ultimo_post = (
            Publicacao.select(Publicacao.id, Publicacao.titulo, Publicacao.criado_em)
            .where(Publicacao.usuario == b.id)
            .order_by(Publicacao.criado_em.desc(), Publicacao.id.desc())
            .first()
        )
        b.ultimo_post = ultimo_post
    return blogs


def excluir_usuario(usuario_id):
    removidos = Usuario.delete().where(Usuario.id == usuario_id).execute()
    return removidos > 0


# Operações da Tabela 2: jogos

def listar_jogos(busca='', genero='', origem='', pagina=1, por_pagina=9):
    consulta = (
        Jogo.select(
            Jogo,
            fn.COALESCE(fn.ROUND(fn.AVG(Publicacao.nota), 1), 0).alias('media_nota'),
            fn.COUNT(Publicacao.id).alias('total_publicacoes')
        )
        .join(Publicacao, JOIN.LEFT_OUTER, on=(Publicacao.jogo == Jogo.id))
        .group_by(Jogo.id)
    )

    filtros = []
    if busca:
        filtros.append(
            (Jogo.titulo.ilike(f"%{busca}%")) | (Jogo.plataforma.ilike(f"%{busca}%"))
        )
    if genero:
        filtros.append(Jogo.genero.ilike(f"%{genero}%"))
    if origem:
        filtros.append(Jogo.origem_dados == origem)

    consulta_contagem = Jogo.select()
    if filtros:
        condicao_combinada = reduce(operator.and_, filtros)
        consulta = consulta.where(condicao_combinada)
        consulta_contagem = consulta_contagem.where(condicao_combinada)

    total_registros = consulta_contagem.count()
    jogos = list(consulta.order_by(Jogo.id.desc()).paginate(pagina, por_pagina))
    generos = [j.genero for j in Jogo.select(Jogo.genero).distinct().order_by(Jogo.genero.asc())]

    return {
        'jogos': jogos,
        'total': total_registros,
        'pagina': pagina,
        'por_pagina': por_pagina,
        'total_paginas': max(1, (total_registros + por_pagina - 1) // por_pagina),
        'generos': generos
    }


def listar_todos_jogos():
    return list(Jogo.select(Jogo.id, Jogo.titulo, Jogo.plataforma, Jogo.ano_lancamento).order_by(Jogo.titulo.asc()))


def listar_jogos_importados(limite=30):
    return list(
        Jogo.select()
        .where(Jogo.origem_dados == 'web_import')
        .order_by(Jogo.id.desc())
        .limit(limite)
    )


def obter_jogo_por_id(jogo_id):
    return Jogo.get_or_none(Jogo.id == jogo_id)


def criar_jogo(titulo, genero, plataforma, ano_lancamento, preco, origem_dados='local'):
    return Jogo.create(
        titulo=titulo.strip(),
        genero=genero.strip(),
        plataforma=plataforma.strip(),
        ano_lancamento=int(ano_lancamento),
        preco=float(preco),
        origem_dados=origem_dados
    )


def atualizar_jogo(jogo_id, titulo, genero, plataforma, ano_lancamento, preco):
    jogo = Jogo.get_or_none(Jogo.id == jogo_id)
    if jogo:
        jogo.titulo = titulo.strip()
        jogo.genero = genero.strip()
        jogo.plataforma = plataforma.strip()
        jogo.ano_lancamento = int(ano_lancamento)
        jogo.preco = float(preco)
        jogo.save()
        return jogo
    return None


def excluir_jogo(jogo_id):
    removidos = Jogo.delete().where(Jogo.id == jogo_id).execute()
    return removidos > 0


# Operações da Tabela 3: publicacoes

def listar_publicacoes(jogo_id=None, usuario_id=None, categoria=None, busca=None, ordenacao='recentes', limite=None):
    consulta = (
        Publicacao.select(
            Publicacao.id,
            Publicacao.usuario.alias('usuario_id'),
            Publicacao.jogo.alias('jogo_id'),
            Publicacao.titulo,
            Publicacao.categoria,
            Publicacao.status_jogo,
            Publicacao.horas_jogadas,
            Publicacao.nota,
            Publicacao.conteudo,
            Publicacao.votos,
            Publicacao.criado_em,
            Usuario.username,
            Usuario.nome_completo,
            Usuario.nome_blog,
            Jogo.titulo.alias('jogo_titulo'),
            Jogo.plataforma.alias('jogo_plataforma'),
            Jogo.genero.alias('jogo_genero'),
            Jogo.ano_lancamento.alias('jogo_ano')
        )
        .join(Usuario, on=(Publicacao.usuario == Usuario.id))
        .switch(Publicacao)
        .join(Jogo, JOIN.LEFT_OUTER, on=(Publicacao.jogo == Jogo.id))
    )

    if jogo_id:
        consulta = consulta.where(Publicacao.jogo == jogo_id)

    if usuario_id:
        consulta = consulta.where(Publicacao.usuario == usuario_id)

    if categoria and categoria in CATEGORIAS_VALIDAS:
        consulta = consulta.where(Publicacao.categoria == categoria)

    if busca and busca.strip():
        termo = f"%{busca.strip()}%"
        consulta = consulta.where(
            (Publicacao.titulo.ilike(termo))
            | (Publicacao.conteudo.ilike(termo))
            | (Usuario.nome_completo.ilike(termo))
            | (Usuario.username.ilike(termo))
        )

    if ordenacao == 'populares':
        consulta = consulta.order_by(Publicacao.votos.desc(), Publicacao.criado_em.desc())
    else:
        consulta = consulta.order_by(Publicacao.criado_em.desc(), Publicacao.id.desc())

    if limite:
        consulta = consulta.limit(int(limite))

    return list(consulta.dicts())


def obter_publicacao_detalhada(publicacao_id):
    consulta = (
        Publicacao.select(
            Publicacao.id,
            Publicacao.usuario.alias('usuario_id'),
            Publicacao.jogo.alias('jogo_id'),
            Publicacao.titulo,
            Publicacao.categoria,
            Publicacao.status_jogo,
            Publicacao.horas_jogadas,
            Publicacao.nota,
            Publicacao.conteudo,
            Publicacao.votos,
            Publicacao.criado_em,
            Usuario.username,
            Usuario.nome_completo,
            Usuario.nome_blog,
            Usuario.bio.alias('usuario_bio'),
            Jogo.titulo.alias('jogo_titulo'),
            Jogo.plataforma.alias('jogo_plataforma'),
            Jogo.genero.alias('jogo_genero'),
            Jogo.ano_lancamento.alias('jogo_ano')
        )
        .join(Usuario, on=(Publicacao.usuario == Usuario.id))
        .switch(Publicacao)
        .join(Jogo, JOIN.LEFT_OUTER, on=(Publicacao.jogo == Jogo.id))
        .where(Publicacao.id == publicacao_id)
    )
    resultados = list(consulta.dicts())
    return resultados[0] if resultados else None


def obter_publicacao_por_id(publicacao_id):
    return Publicacao.get_or_none(Publicacao.id == publicacao_id)


def criar_publicacao(
    usuario_id,
    titulo,
    conteudo,
    jogo_id=None,
    nota=None,
    categoria='livre',
    status_jogo='Postagem Livre',
    horas_jogadas=0
):
    categoria_valida = categoria if categoria in CATEGORIAS_VALIDAS else 'livre'
    jogo_fk = int(jogo_id) if jogo_id else None
    nota_val = int(nota) if (jogo_fk and nota is not None and str(nota).strip() != '') else None
    status_limpo = (status_jogo or ('Zerado (História)' if jogo_fk else 'Postagem Livre')).strip()[:30]
    try:
        horas = max(0, int(horas_jogadas or 0)) if jogo_fk else 0
    except (ValueError, TypeError):
        horas = 0

    return Publicacao.create(
        usuario=int(usuario_id),
        jogo=jogo_fk,
        titulo=(titulo or 'Nova Publicação').strip()[:150],
        categoria=categoria_valida,
        status_jogo=status_limpo,
        horas_jogadas=horas,
        nota=nota_val,
        conteudo=conteudo.strip(),
        votos=0
    )


def atualizar_publicacao(
    publicacao_id,
    titulo,
    conteudo,
    jogo_id=None,
    nota=None,
    categoria='livre',
    status_jogo='Postagem Livre',
    horas_jogadas=0
):
    pub = Publicacao.get_or_none(Publicacao.id == publicacao_id)
    if not pub:
        return None

    jogo_fk = int(jogo_id) if jogo_id else None
    pub.jogo = jogo_fk
    pub.titulo = (titulo or 'Nova Publicação').strip()[:150]
    if categoria in CATEGORIAS_VALIDAS:
        pub.categoria = categoria
    pub.status_jogo = (status_jogo or ('Zerado (História)' if jogo_fk else 'Postagem Livre')).strip()[:30]
    if jogo_fk:
        try:
            pub.horas_jogadas = max(0, int(horas_jogadas or 0))
        except (ValueError, TypeError):
            pub.horas_jogadas = 0
        pub.nota = int(nota) if (nota is not None and str(nota).strip() != '') else None
    else:
        pub.horas_jogadas = 0
        pub.nota = None
    pub.conteudo = conteudo.strip()
    pub.save()
    return pub


def votar_publicacao(publicacao_id, direcao='up'):
    pub = Publicacao.get_or_none(Publicacao.id == publicacao_id)
    if not pub:
        return None
    if direcao == 'down':
        pub.votos = max(0, (pub.votos or 0) - 1)
    else:
        pub.votos = (pub.votos or 0) + 1
    pub.save()
    return pub


def excluir_publicacao(publicacao_id):
    removidos = Publicacao.delete().where(Publicacao.id == publicacao_id).execute()
    return removidos > 0


# Destaques e Estatísticas da Plataforma

def obter_destaques_comunidade():
    melhores_jogos = list(
        Jogo.select(
            Jogo,
            fn.COALESCE(fn.ROUND(fn.AVG(Publicacao.nota), 1), 0).alias('media_nota'),
            fn.COUNT(Publicacao.id).alias('total_publicacoes')
        )
        .join(Publicacao, JOIN.INNER, on=(Publicacao.jogo == Jogo.id))
        .where(Publicacao.nota.is_null(False))
        .group_by(Jogo.id)
        .order_by(
            SQL('media_nota').desc(),
            SQL('total_publicacoes').desc()
        )
        .limit(5)
    )

    jogos_recentes = list(
        Jogo.select()
        .order_by(Jogo.id.desc())
        .limit(5)
    )

    blogs_destaque = listar_blogs(limite=5)

    return {
        'melhores_jogos': melhores_jogos,
        'jogos_recentes': jogos_recentes,
        'blogs_destaque': blogs_destaque
    }


def obter_estatisticas_usuario(usuario_id):
    if not usuario_id:
        return {'posts': 0, 'jogos': 0, 'curtidas': 0}

    pubs = list(
        Publicacao.select(Publicacao.jogo, Publicacao.votos)
        .where(Publicacao.usuario == usuario_id)
        .dicts()
    )
    return {
        'posts': len(pubs),
        'jogos': len({p['jogo'] for p in pubs if p.get('jogo')}),
        'curtidas': sum(p.get('votos') or 0 for p in pubs)
    }


def obter_estatisticas():
    return {
        'usuarios': Usuario.select().count(),
        'jogos': Jogo.select().count(),
        'importados': Jogo.select().where(Jogo.origem_dados == 'web_import').count(),
        'publicacoes': Publicacao.select().count(),
        'zerados': Publicacao.select().where(Publicacao.categoria == 'zerado').count(),
        'detonados': Publicacao.select().where(Publicacao.categoria == 'detonado').count(),
        'sgbd': MOTOR_ATIVO
    }
