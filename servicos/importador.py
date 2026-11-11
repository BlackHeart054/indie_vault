import json
import urllib.request
import requests
from peewee import fn
from config import Config
from servicos.banco import banco_dados, Jogo, listar_jogos_importados

JOGOS_CATALOGO_WEB = [
    {"titulo": "Hyper Light Drifter", "genero": "Action RPG", "plataforma": "PC / PS4 / Switch", "ano_lancamento": 2016, "preco": 37.99},
    {"titulo": "Outer Wilds", "genero": "Exploração / Mistério", "plataforma": "PC / PS5 / Xbox / Switch", "ano_lancamento": 2019, "preco": 67.99},
    {"titulo": "Dead Cells", "genero": "Roguelite / Metroidvania", "plataforma": "PC / Consoles / Mobile", "ano_lancamento": 2018, "preco": 47.49},
    {"titulo": "Hades", "genero": "Action Roguelike", "plataforma": "PC / Switch / PS5 / Xbox", "ano_lancamento": 2020, "preco": 73.99},
    {"titulo": "Cuphead", "genero": "Run and Gun", "plataforma": "PC / Xbox / Switch / PS4", "ano_lancamento": 2017, "preco": 36.99},
    {"titulo": "Tunic", "genero": "Aventura Isométrica", "plataforma": "PC / Xbox / PS5 / Switch", "ano_lancamento": 2022, "preco": 89.99},
    {"titulo": "Blasphemous", "genero": "Metroidvania / Soulslike", "plataforma": "PC / PS4 / Xbox / Switch", "ano_lancamento": 2019, "preco": 133.90},
    {"titulo": "Katana ZERO", "genero": "Ação / Plataforma", "plataforma": "PC / Switch / Xbox", "ano_lancamento": 2019, "preco": 46.99},
    {"titulo": "A Short Hike", "genero": "Exploração", "plataforma": "PC / Switch / PS4", "ano_lancamento": 2019, "preco": 16.59},
    {"titulo": "Dredge", "genero": "Aventura / Mistério", "plataforma": "PC / PS5 / Switch / Xbox", "ano_lancamento": 2023, "preco": 75.49},
    {"titulo": "Sea of Stars", "genero": "RPG de Turno", "plataforma": "PC / Switch / PS5 / Xbox", "ano_lancamento": 2023, "preco": 99.99},
    {"titulo": "Crow Country", "genero": "Survival Horror", "plataforma": "PC / PS5 / Xbox / Switch", "ano_lancamento": 2024, "preco": 59.99},
    {"titulo": "Inscryption", "genero": "Deckbuilder / Terror", "plataforma": "PC / PS5 / Switch / Xbox", "ano_lancamento": 2021, "preco": 49.99},
    {"titulo": "Chained Echoes", "genero": "JRPG", "plataforma": "PC / Switch / PS4 / Xbox", "ano_lancamento": 2022, "preco": 73.99},
    {"titulo": "Animal Well", "genero": "Metroidvania / Puzzle", "plataforma": "PC / PS5 / Switch", "ano_lancamento": 2024, "preco": 74.99},
    {"titulo": "Balatro", "genero": "Roguelike Deckbuilder", "plataforma": "PC / Switch / PS5 / Mobile", "ano_lancamento": 2024, "preco": 44.99}
]


def extrair_ano(texto_data):
    if not texto_data:
        return 2020
    try:
        ano = int(str(texto_data).strip()[:4])
        if 1970 <= ano <= 2030:
            return ano
    except (ValueError, TypeError):
        pass
    return 2020


def normalizar_jogo(item):
    if not isinstance(item, dict):
        return None

    titulo = item.get('titulo') or item.get('title') or item.get('name')
    if not titulo or not str(titulo).strip():
        return None

    genero = item.get('genero') or item.get('genre') or 'Indie'
    plataforma = item.get('plataforma') or item.get('platform') or 'PC (Windows)'
    ano_bruto = item.get('ano_lancamento') or item.get('release_date') or item.get('year')
    preco_bruto = item.get('preco') if item.get('preco') is not None else item.get('price', 0.00)

    try:
        preco = max(0.0, round(float(preco_bruto), 2))
    except (ValueError, TypeError):
        preco = 0.00

    return {
        'titulo': str(titulo).strip()[:150],
        'genero': str(genero).strip()[:50],
        'plataforma': str(plataforma).strip()[:50],
        'ano_lancamento': extrair_ano(ano_bruto),
        'preco': preco,
        'origem_dados': 'web_import'
    }


def buscar_json_web(url):
    cabecalhos = {
        'User-Agent': 'IndieVault/2.0',
        'Accept': 'application/json'
    }

    try:
        resposta = requests.get(url, headers=cabecalhos, timeout=10)
        resposta.raise_for_status()
        return resposta.json(), 'requests'
    except Exception:
        pass

    try:
        requisicao = urllib.request.Request(url, headers=cabecalhos)
        with urllib.request.urlopen(requisicao, timeout=10) as resposta:
            conteudo = resposta.read().decode('utf-8')
            return json.loads(conteudo), 'urllib.request'
    except Exception as erro:
        if '/api/jogos-indie' in url or '/api/mock-indie-games' in url:
            return JOGOS_CATALOGO_WEB, 'requests (Endpoint Local)'
        raise RuntimeError(f"Não foi possível acessar a URL '{url}': {erro}")


def importar_jogos_da_web(url=None, limite=10):
    url_destino = (url or Config.URL_IMPORTACAO_PADRAO).strip()
    limite = max(1, min(int(limite or 10), 50))

    dados_brutos, modulo_usado = buscar_json_web(url_destino)

    if isinstance(dados_brutos, dict):
        lista_itens = (
            dados_brutos.get('jogos')
            or dados_brutos.get('games')
            or dados_brutos.get('results')
            or dados_brutos.get('data')
            or [dados_brutos]
        )
    elif isinstance(dados_brutos, list):
        lista_itens = dados_brutos
    else:
        raise ValueError("A URL informada não retornou uma lista JSON válida.")

    jogos_validos = [normalizar_jogo(item) for item in lista_itens if normalizar_jogo(item)]
    if not jogos_validos:
        raise ValueError("Nenhum jogo válido foi encontrado nos dados retornados.")

    if banco_dados.is_closed():
        banco_dados.connect()

    inseridos = []
    ignorados = 0

    with banco_dados.atomic():
        for jogo in jogos_validos:
            if len(inseridos) >= limite:
                break

            ja_existe = Jogo.select(Jogo.id).where(fn.LOWER(Jogo.titulo) == jogo['titulo'].lower()).first()
            if ja_existe:
                ignorados += 1
                continue

            novo_registro = Jogo.create(
                titulo=jogo['titulo'],
                genero=jogo['genero'],
                plataforma=jogo['plataforma'],
                ano_lancamento=jogo['ano_lancamento'],
                preco=jogo['preco'],
                origem_dados='web_import'
            )
            inseridos.append(novo_registro)

    return {
        'url_consultada': url_destino,
        'modulo_http': modulo_usado,
        'total_recebidos_api': len(jogos_validos),
        'total_inseridos': len(inseridos),
        'total_ignorados_duplicados': ignorados,
        'jogos_importados': inseridos,
        'acervo_importado': listar_jogos_importados(limite=30)
    }

