import os
from functools import wraps
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, send_file, jsonify
)
from werkzeug.middleware.proxy_fix import ProxyFix
from config import Config
from servicos import banco
from servicos import importador
from servicos import exportador

app = Flask(__name__)
app.config.from_object(Config)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

with app.app_context():
    sucesso, mensagem = banco.inicializar_banco()
    print(f"[IndieVault] {mensagem}")


@app.before_request
def abrir_conexao():
    try:
        if banco.banco_dados.is_closed():
            banco.banco_dados.connect(reuse_if_open=True)
    except Exception:
        pass


@app.teardown_request
def fechar_conexao(excecao):
    try:
        if not banco.banco_dados.is_closed():
            banco.banco_dados.close()
    except Exception:
        pass


@app.context_processor
def injetar_contexto_global():
    return {
        'sgbd_ativo': banco.obter_motor_ativo(),
        'curtidas_usuario': set(session.get('curtidas', []))
    }


def login_obrigatorio(funcao):
    @wraps(funcao)
    def funcao_decorada(*args, **kwargs):
        if 'usuario_id' not in session:
            flash('Entre na sua conta para acessar os blogs da comunidade.', 'erro')
            return redirect(url_for('login'))
        return funcao(*args, **kwargs)
    return funcao_decorada


@app.route('/')
def inicio():
    if 'usuario_id' in session:
        return redirect(url_for('menu_principal'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'usuario_id' in session and request.method == 'GET':
        return redirect(url_for('menu_principal'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        senha = request.form.get('senha', '')

        if not username or not senha:
            flash('Informe seu nickname e senha.', 'erro')
            return render_template('login.html')

        try:
            usuario = banco.autenticar_usuario(username, senha)
            if usuario:
                session['usuario_id'] = usuario['id']
                session['username'] = usuario['username']
                session['nome_completo'] = usuario['nome_completo']
                session['nome_blog'] = usuario['nome_blog']
                session['curtidas'] = session.get('curtidas', [])
                flash(f"Bem-vindo de volta, {usuario['nome_completo']}!", 'sucesso')
                return redirect(url_for('menu_principal'))
            flash('Nickname ou senha incorretos.', 'erro')
        except Exception as erro:
            flash(f'Erro ao autenticar: {erro}', 'erro')

    return render_template('login.html')


@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if 'usuario_id' in session and request.method == 'GET':
        return redirect(url_for('menu_principal'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip().lstrip('@')
        nome_completo = request.form.get('nome_completo', '').strip()
        nome_blog = request.form.get('nome_blog', '').strip()
        bio = request.form.get('bio', '').strip()
        senha = request.form.get('senha', '')
        confirmar_senha = request.form.get('confirmar_senha', '')

        if not username or not nome_completo or not senha:
            flash('Preencha todos os campos obrigatórios.', 'erro')
            return render_template('cadastro.html', form=request.form)

        if ' ' in username:
            flash('O nickname não pode conter espaços.', 'erro')
            return render_template('cadastro.html', form=request.form)

        if senha != confirmar_senha:
            flash('As senhas informadas não coincidem.', 'erro')
            return render_template('cadastro.html', form=request.form)

        if len(senha) < 4:
            flash('A senha deve ter pelo menos 4 caracteres.', 'erro')
            return render_template('cadastro.html', form=request.form)

        try:
            novo_usuario = banco.criar_usuario(
                username=username,
                senha=senha,
                nome_completo=nome_completo,
                bio=bio,
                nome_blog=nome_blog
            )
            flash(f"Blog '{novo_usuario['nome_blog']}' criado para @{novo_usuario['username']}! Faça login para publicar.", 'sucesso')
            return redirect(url_for('login'))
        except Exception as erro:
            if 'unique' in str(erro).lower() or 'duplicate' in str(erro).lower():
                flash(f"O nickname '@{username}' já está em uso.", 'erro')
            else:
                flash(f"Erro ao criar conta: {erro}", 'erro')
            return render_template('cadastro.html', form=request.form)

    return render_template('cadastro.html', form=None)


@app.route('/sair')
def sair():
    session.clear()
    flash('Você saiu da sua conta.', 'info')
    return redirect(url_for('login'))


@app.route('/menu')
@login_obrigatorio
def menu_principal():
    filtro_categoria = request.args.get('categoria', '').strip()
    ordenacao = request.args.get('ordem', 'recentes').strip()

    meus_stats = {'posts': 0, 'jogos': 0, 'curtidas': 0}
    publicacoes = []
    destaques = {'melhores_jogos': [], 'jogos_recentes': [], 'blogs_destaque': []}

    try:
        meus_stats = banco.obter_estatisticas_usuario(session.get('usuario_id'))
        publicacoes = banco.listar_publicacoes(
            categoria=filtro_categoria if filtro_categoria else None,
            ordenacao=ordenacao,
            limite=15
        )
        destaques = banco.obter_destaques_comunidade()
    except Exception as erro:
        flash(f'Erro ao carregar o feed: {erro}', 'erro')

    return render_template(
        'menu.html',
        meus_stats=meus_stats,
        publicacoes=publicacoes,
        destaques=destaques,
        filtro_categoria=filtro_categoria,
        ordenacao=ordenacao
    )


@app.route('/blogs')
@login_obrigatorio
def listar_blogs_rota():
    busca = request.args.get('busca', '').strip()
    blogs = banco.listar_blogs(busca=busca)
    return render_template('blogs_lista.html', blogs=blogs, filtro_busca=busca)


@app.route('/blog/<username>')
@login_obrigatorio
def ver_blog_usuario(username):
    autor = banco.obter_usuario_por_username(username)
    if not autor:
        flash('Blog não encontrado.', 'erro')
        return redirect(url_for('listar_blogs_rota'))

    filtro_categoria = request.args.get('categoria', '').strip()
    publicacoes = banco.listar_publicacoes(
        usuario_id=autor.id,
        categoria=filtro_categoria if filtro_categoria else None
    )
    stats_autor = banco.obter_estatisticas_usuario(autor.id)

    return render_template(
        'blog_usuario.html',
        autor=autor,
        publicacoes=publicacoes,
        total_publicacoes=stats_autor['posts'],
        total_curtidas=stats_autor['curtidas'],
        jogos_unicos=stats_autor['jogos'],
        filtro_categoria=filtro_categoria
    )


@app.route('/sobre')
@login_obrigatorio
def sobre():
    dados_projeto = {
        'nome_sistema': 'IndieVault - Blogs Gamers',
        'tema_escolhido': (
            'Rede social simples de blogs gamers, tipo um Blogspot voltado pra jogos, onde cada pessoa tem '
            'seu espaço pra postar o que quiser (textos livres, jogos zerados, detonados ou reviews) e ver os posts da galera.'
        ),
        'disciplina': 'Tópicos Especiais em Informática (Análise e Desenvolvimento de Sistemas)',
        'instituicao': 'Centro Paula Souza / Fatec Ribeirão Preto',
        'objetivo': (
            'Fazer uma aplicação web em Python (Flask + Peewee ORM) onde usuários criam seus blogs, publicam '
            'textos livres ou ligados a um catálogo de jogos, importam títulos da Web (Requests / URLlib) e '
            'exportam os dados do banco em JSON compactado em ZIP.'
        ),
        'desenvolvedores': [
            {
                'nome_completo': 'Lucas da Silva de Menezes',
                'ra': '2840482313015',
                'curso': 'Análise e Desenvolvimento de Sistemas',
                'instituicao': 'Fatec Ribeirão Preto'
            }
        ]
    }
    return render_template('sobre.html', projeto=dados_projeto)


@app.route('/perfil')
@login_obrigatorio
def meu_perfil():
    usuario_id = session.get('usuario_id')
    usuario_atual = banco.obter_usuario_por_id(usuario_id)
    minhas_publicacoes = banco.listar_publicacoes(usuario_id=usuario_id)
    total_curtidas = sum(p.get('votos') or 0 for p in minhas_publicacoes)

    return render_template(
        'perfil.html',
        usuario_atual=usuario_atual,
        minhas_publicacoes=minhas_publicacoes,
        total_curtidas=total_curtidas
    )


@app.route('/perfil/editar', methods=['GET', 'POST'])
@login_obrigatorio
def editar_perfil():
    usuario_id = session.get('usuario_id')
    usuario_atual = banco.obter_usuario_por_id(usuario_id)

    if request.method == 'POST':
        username = request.form.get('username', '').strip().lstrip('@')
        nome_completo = request.form.get('nome_completo', '').strip()
        nome_blog = request.form.get('nome_blog', '').strip()
        bio = request.form.get('bio', '').strip()
        nova_senha = request.form.get('nova_senha', '').strip()

        if not username or not nome_completo:
            flash('Nickname e nome são obrigatórios.', 'erro')
            return render_template('perfil_editar.html', usuario=usuario_atual)

        if ' ' in username:
            flash('O nickname não pode conter espaços.', 'erro')
            return render_template('perfil_editar.html', usuario=usuario_atual)

        if nova_senha and len(nova_senha) < 4:
            flash('A nova senha deve ter pelo menos 4 caracteres.', 'erro')
            return render_template('perfil_editar.html', usuario=usuario_atual)

        try:
            atualizado = banco.atualizar_usuario(
                usuario_id=usuario_id,
                username=username,
                nome_completo=nome_completo,
                bio=bio,
                nome_blog=nome_blog,
                nova_senha=nova_senha if nova_senha else None
            )
            session['username'] = atualizado['username']
            session['nome_completo'] = atualizado['nome_completo']
            session['nome_blog'] = atualizado['nome_blog']
            flash('Seu perfil e blog foram atualizados com sucesso!', 'sucesso')
            return redirect(url_for('meu_perfil'))
        except Exception as erro:
            if 'unique' in str(erro).lower() or 'duplicate' in str(erro).lower():
                flash(f"O nickname '@{username}' já pertence a outro membro.", 'erro')
            else:
                flash(f'Erro ao atualizar perfil: {erro}', 'erro')

    return render_template('perfil_editar.html', usuario=usuario_atual)


@app.route('/perfil/excluir', methods=['POST'])
@login_obrigatorio
def excluir_minha_conta():
    usuario_id = session.get('usuario_id')
    if banco.Usuario.select().count() <= 1:
        flash('Não é possível excluir o único membro restante na plataforma.', 'erro')
        return redirect(url_for('meu_perfil'))

    banco.excluir_usuario(usuario_id)
    session.clear()
    flash('Sua conta e seu blog foram encerrados com sucesso.', 'info')
    return redirect(url_for('login'))


@app.route('/jogos')
@login_obrigatorio
def listar_jogos_rota():
    busca = request.args.get('busca', '').strip()
    genero = request.args.get('genero', '').strip()
    origem = request.args.get('origem', '').strip()
    try:
        pagina = max(1, int(request.args.get('pagina', 1)))
    except ValueError:
        pagina = 1

    resultado = banco.listar_jogos(busca=busca, genero=genero, origem=origem, pagina=pagina, por_pagina=9)

    return render_template(
        'jogos_lista.html',
        jogos=resultado['jogos'],
        total=resultado['total'],
        pagina=resultado['pagina'],
        total_paginas=resultado['total_paginas'],
        generos=resultado['generos'],
        filtro_busca=busca,
        filtro_genero=genero,
        filtro_origem=origem
    )


@app.route('/jogos/novo', methods=['GET', 'POST'])
@login_obrigatorio
def novo_jogo():
    if request.method == 'POST':
        titulo = request.form.get('titulo', '').strip()
        genero = request.form.get('genero', '').strip()
        plataforma = request.form.get('plataforma', '').strip()
        ano_lancamento = request.form.get('ano_lancamento', '').strip()
        preco = request.form.get('preco', '0.00').strip().replace(',', '.')

        if not titulo or not genero or not plataforma or not ano_lancamento:
            flash('Preencha todos os campos obrigatórios do jogo.', 'erro')
            return render_template('jogo_form.html', modo='novo', jogo=request.form)

        try:
            jogo = banco.criar_jogo(titulo, genero, plataforma, int(ano_lancamento), float(preco), origem_dados='local')
            flash(f"Jogo '{jogo['titulo']}' adicionado ao catálogo!", 'sucesso')
            return redirect(url_for('listar_jogos_rota'))
        except Exception as erro:
            flash(f'Erro ao adicionar jogo: {erro}', 'erro')
            return render_template('jogo_form.html', modo='novo', jogo=request.form)

    return render_template('jogo_form.html', modo='novo', jogo=None)


@app.route('/jogos/editar/<int:jogo_id>', methods=['GET', 'POST'])
@login_obrigatorio
def editar_jogo(jogo_id):
    jogo_atual = banco.obter_jogo_por_id(jogo_id)
    if not jogo_atual:
        flash('Jogo não encontrado.', 'erro')
        return redirect(url_for('listar_jogos_rota'))

    if request.method == 'POST':
        titulo = request.form.get('titulo', '').strip()
        genero = request.form.get('genero', '').strip()
        plataforma = request.form.get('plataforma', '').strip()
        ano_lancamento = request.form.get('ano_lancamento', '').strip()
        preco = (request.form.get('preco') or str(jogo_atual.preco or '0.00')).strip().replace(',', '.')

        if not titulo or not genero or not plataforma or not ano_lancamento:
            flash('Preencha todos os campos obrigatórios.', 'erro')
            return render_template('jogo_form.html', modo='editar', jogo=jogo_atual)

        try:
            atualizado = banco.atualizar_jogo(
                jogo_id, titulo, genero, plataforma, int(ano_lancamento), float(preco)
            )
            flash(f"Informações de '{atualizado['titulo']}' atualizadas!", 'sucesso')
            return redirect(url_for('listar_jogos_rota'))
        except Exception as erro:
            flash(f'Erro ao atualizar jogo: {erro}', 'erro')

    return render_template('jogo_form.html', modo='editar', jogo=jogo_atual)


@app.route('/jogos/excluir/<int:jogo_id>', methods=['POST'])
@login_obrigatorio
def excluir_jogo_rota(jogo_id):
    if banco.excluir_jogo(jogo_id):
        flash('Jogo removido do catálogo.', 'sucesso')
    else:
        flash('Jogo não encontrado.', 'erro')
    return redirect(url_for('listar_jogos_rota'))


@app.route('/publicacoes')
@login_obrigatorio
def listar_publicacoes_rota():
    busca = request.args.get('busca', '').strip()
    filtro_jogo_id = request.args.get('jogo_id', '').strip()
    filtro_usuario_id = request.args.get('usuario_id', '').strip()
    filtro_categoria = request.args.get('categoria', '').strip()
    ordenacao = request.args.get('ordem', 'recentes').strip()

    jogos = banco.listar_todos_jogos()
    autores = banco.listar_usuarios()
    publicacoes = banco.listar_publicacoes(
        jogo_id=int(filtro_jogo_id) if filtro_jogo_id.isdigit() else None,
        usuario_id=int(filtro_usuario_id) if filtro_usuario_id.isdigit() else None,
        categoria=filtro_categoria if filtro_categoria else None,
        busca=busca,
        ordenacao=ordenacao
    )

    return render_template(
        'publicacoes_lista.html',
        publicacoes=publicacoes,
        jogos=jogos,
        autores=autores,
        filtro_busca=busca,
        filtro_jogo_id=int(filtro_jogo_id) if filtro_jogo_id.isdigit() else None,
        filtro_usuario_id=int(filtro_usuario_id) if filtro_usuario_id.isdigit() else None,
        filtro_categoria=filtro_categoria,
        ordenacao=ordenacao
    )


@app.route('/publicacoes/<int:publicacao_id>')
@login_obrigatorio
def ver_publicacao(publicacao_id):
    publicacao = banco.obter_publicacao_detalhada(publicacao_id)
    if not publicacao:
        flash('Publicação não encontrada.', 'erro')
        return redirect(url_for('listar_publicacoes_rota'))
    return render_template('publicacao_detalhe.html', publicacao=publicacao)


@app.route('/publicacoes/nova', methods=['GET', 'POST'])
@login_obrigatorio
def nova_publicacao():
    jogos = banco.listar_todos_jogos()
    jogo_selecionado = request.args.get('jogo_id', type=int)

    if request.method == 'POST':
        jogo_id = request.form.get('jogo_id', '').strip()
        titulo = request.form.get('titulo', '').strip()
        categoria = request.form.get('categoria', 'livre').strip()
        status_jogo = request.form.get('status_jogo', 'Postagem Livre').strip()
        horas_jogadas = request.form.get('horas_jogadas', '0').strip()
        nota = request.form.get('nota', '').strip()
        conteudo = request.form.get('conteudo', '').strip()
        usuario_id = session.get('usuario_id')

        if not titulo or not conteudo:
            flash('Informe o título e o conteúdo da sua publicação.', 'erro')
            return render_template('publicacao_form.html', modo='nova', publicacao=request.form, jogos=jogos, jogo_selecionado=jogo_selecionado)

        try:
            nota_val = None
            if jogo_id and nota != '':
                nota_val = int(nota)
                if not (0 <= nota_val <= 10):
                    raise ValueError('A nota deve estar entre 0 e 10.')

            nova = banco.criar_publicacao(
                usuario_id=usuario_id,
                titulo=titulo,
                conteudo=conteudo,
                jogo_id=int(jogo_id) if jogo_id.isdigit() else None,
                nota=nota_val,
                categoria=categoria,
                status_jogo=status_jogo if jogo_id else 'Postagem Livre',
                horas_jogadas=horas_jogadas
            )
            flash('Publicação adicionada ao seu blog!', 'sucesso')
            return redirect(url_for('ver_publicacao', publicacao_id=nova.id))
        except Exception as erro:
            flash(f'Erro ao publicar: {erro}', 'erro')
            return render_template('publicacao_form.html', modo='nova', publicacao=request.form, jogos=jogos, jogo_selecionado=jogo_selecionado)

    return render_template('publicacao_form.html', modo='nova', publicacao=None, jogos=jogos, jogo_selecionado=jogo_selecionado)


@app.route('/publicacoes/editar/<int:publicacao_id>', methods=['GET', 'POST'])
@login_obrigatorio
def editar_publicacao(publicacao_id):
    publicacao_atual = banco.obter_publicacao_por_id(publicacao_id)
    if not publicacao_atual:
        flash('Publicação não encontrada.', 'erro')
        return redirect(url_for('listar_publicacoes_rota'))

    if publicacao_atual.usuario_id != session.get('usuario_id'):
        flash('Você só pode editar publicações do seu próprio blog.', 'erro')
        return redirect(url_for('ver_publicacao', publicacao_id=publicacao_id))

    jogos = banco.listar_todos_jogos()

    if request.method == 'POST':
        jogo_id = request.form.get('jogo_id', '').strip()
        titulo = request.form.get('titulo', '').strip()
        categoria = request.form.get('categoria', 'livre').strip()
        status_jogo = request.form.get('status_jogo', 'Postagem Livre').strip()
        horas_jogadas = request.form.get('horas_jogadas', '0').strip()
        nota = request.form.get('nota', '').strip()
        conteudo = request.form.get('conteudo', '').strip()

        if not titulo or not conteudo:
            flash('Título e conteúdo são obrigatórios.', 'erro')
            return render_template('publicacao_form.html', modo='editar', publicacao=publicacao_atual, jogos=jogos, jogo_selecionado=None)

        try:
            nota_val = None
            if jogo_id and nota != '':
                nota_val = int(nota)
                if not (0 <= nota_val <= 10):
                    raise ValueError('A nota deve estar entre 0 e 10.')

            banco.atualizar_publicacao(
                publicacao_id=publicacao_id,
                titulo=titulo,
                conteudo=conteudo,
                jogo_id=int(jogo_id) if jogo_id.isdigit() else None,
                nota=nota_val,
                categoria=categoria,
                status_jogo=status_jogo if jogo_id else 'Postagem Livre',
                horas_jogadas=horas_jogadas
            )
            flash('Publicação atualizada com sucesso!', 'sucesso')
            return redirect(url_for('ver_publicacao', publicacao_id=publicacao_id))
        except Exception as erro:
            flash(f'Erro ao atualizar publicação: {erro}', 'erro')

    return render_template('publicacao_form.html', modo='editar', publicacao=publicacao_atual, jogos=jogos, jogo_selecionado=None)


@app.route('/publicacoes/votar/<int:publicacao_id>', methods=['POST'])
@login_obrigatorio
def votar_publicacao_rota(publicacao_id):
    curtidas = list(session.get('curtidas', []))
    if publicacao_id in curtidas:
        banco.votar_publicacao(publicacao_id, direcao='down')
        curtidas.remove(publicacao_id)
    else:
        banco.votar_publicacao(publicacao_id, direcao='up')
        curtidas.append(publicacao_id)
    session['curtidas'] = curtidas
    return redirect(request.referrer or url_for('menu_principal'))


@app.route('/publicacoes/excluir/<int:publicacao_id>', methods=['POST'])
@login_obrigatorio
def excluir_publicacao_rota(publicacao_id):
    pub = banco.obter_publicacao_por_id(publicacao_id)
    if not pub:
        flash('Publicação não encontrada.', 'erro')
        return redirect(url_for('listar_publicacoes_rota'))

    if pub.usuario_id != session.get('usuario_id'):
        flash('Você só pode excluir publicações do seu próprio blog.', 'erro')
        return redirect(url_for('ver_publicacao', publicacao_id=publicacao_id))

    banco.excluir_publicacao(publicacao_id)
    flash('Publicação excluída.', 'sucesso')
    return redirect(request.referrer or url_for('meu_perfil'))


@app.route('/api/jogos-indie')
def api_jogos_indie():
    return jsonify(importador.JOGOS_CATALOGO_WEB)


@app.route('/importar', methods=['GET', 'POST'])
@login_obrigatorio
def importar_dados():
    resultado = None
    url_padrao = Config.URL_IMPORTACAO_PADRAO

    if request.method == 'POST':
        url_informada = request.form.get('url_api', url_padrao).strip()
        limite = request.form.get('limite', '8').strip()

        try:
            resultado = importador.importar_jogos_da_web(url=url_informada, limite=int(limite))
            if resultado['total_inseridos'] > 0:
                flash(f"{resultado['total_inseridos']} novo(s) jogo(s) importado(s) com sucesso!", 'sucesso')
            else:
                flash('Consulta realizada: os jogos retornados já constam no catálogo.', 'info')
        except Exception as erro:
            flash(f'Erro na importação: {erro}', 'erro')

    acervo_importado = banco.listar_jogos_importados(limite=30)

    return render_template(
        'importar.html',
        url_padrao=url_padrao,
        resultado=resultado,
        acervo_importado=acervo_importado
    )


@app.route('/exportar')
@login_obrigatorio
def exportar_dados():
    resumo = exportador.obter_resumo_exportacao()
    previa_json = exportador.obter_previa_json()
    return render_template('exportar.html', resumo=resumo, previa_json=previa_json)


@app.route('/exportar/download', methods=['POST', 'GET'])
@login_obrigatorio
def baixar_backup_zip():
    try:
        buffer_zip = exportador.gerar_arquivo_zip()
        return send_file(
            buffer_zip,
            mimetype='application/zip',
            as_attachment=True,
            download_name='indievault_backup.zip'
        )
    except Exception as erro:
        flash(f'Erro ao gerar arquivo ZIP: {erro}', 'erro')
        return redirect(url_for('exportar_dados'))


if __name__ == '__main__':
    porta = int(os.getenv('PORT', '5000'))
    host = os.getenv('HOST', '127.0.0.1')
    modo_debug = os.getenv('FLASK_DEBUG', 'true').lower() == 'true'
    app.run(host=host, port=porta, debug=modo_debug, threaded=True)
