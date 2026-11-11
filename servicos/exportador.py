import io
import json
import zipfile
from datetime import datetime, date
from decimal import Decimal
from servicos.banco import banco_dados, Usuario, Jogo, Publicacao, obter_motor_ativo


def converter_para_json(objeto):
    if isinstance(objeto, (datetime, date)):
        return objeto.isoformat()
    if isinstance(objeto, Decimal):
        return float(objeto)
    raise TypeError(f"Tipo {type(objeto)} não serializável.")


def obter_resumo_exportacao():
    if banco_dados.is_closed():
        banco_dados.connect()

    total_usuarios = Usuario.select().count()
    total_jogos = Jogo.select().count()
    total_publicacoes = Publicacao.select().count()

    return {
        'usuarios': total_usuarios,
        'jogos': total_jogos,
        'publicacoes': total_publicacoes,
        'total_registros': total_usuarios + total_jogos + total_publicacoes,
        'sgbd': obter_motor_ativo()
    }


def coletar_todos_os_dados():
    if banco_dados.is_closed():
        banco_dados.connect()

    dados_usuarios = list(
        Usuario.select(
            Usuario.id,
            Usuario.username,
            Usuario.nome_completo,
            Usuario.nome_blog,
            Usuario.bio,
            Usuario.criado_em
        ).order_by(Usuario.id.asc()).dicts()
    )
    dados_jogos = list(Jogo.select().order_by(Jogo.id.asc()).dicts())
    dados_publicacoes = list(
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
            Publicacao.criado_em
        ).order_by(Publicacao.id.asc()).dicts()
    )

    return {
        'sistema': 'IndieVault - Rede de Blogs Gamers',
        'exportado_em': datetime.now().isoformat(),
        'sgbd_origem': obter_motor_ativo(),
        'tabelas': {
            'usuarios': dados_usuarios,
            'jogos': dados_jogos,
            'publicacoes': dados_publicacoes
        }
    }


def obter_previa_json():
    pacote = coletar_todos_os_dados()
    return json.dumps(pacote, indent=2, ensure_ascii=False, default=converter_para_json)


def gerar_arquivo_zip():
    pacote = coletar_todos_os_dados()
    dados_usuarios = pacote['tabelas']['usuarios']
    dados_jogos = pacote['tabelas']['jogos']
    dados_publicacoes = pacote['tabelas']['publicacoes']

    json_completo = json.dumps(pacote, indent=4, ensure_ascii=False, default=converter_para_json)
    json_usuarios = json.dumps(dados_usuarios, indent=4, ensure_ascii=False, default=converter_para_json)
    json_jogos = json.dumps(dados_jogos, indent=4, ensure_ascii=False, default=converter_para_json)
    json_publicacoes = json.dumps(dados_publicacoes, indent=4, ensure_ascii=False, default=converter_para_json)

    buffer_memoria = io.BytesIO()
    with zipfile.ZipFile(buffer_memoria, mode='w', compression=zipfile.ZIP_DEFLATED) as arquivo_zip:
        arquivo_zip.writestr('indievault_completo.json', json_completo.encode('utf-8'))
        arquivo_zip.writestr('usuarios.json', json_usuarios.encode('utf-8'))
        arquivo_zip.writestr('jogos.json', json_jogos.encode('utf-8'))
        arquivo_zip.writestr('publicacoes.json', json_publicacoes.encode('utf-8'))

    buffer_memoria.seek(0)
    return buffer_memoria

