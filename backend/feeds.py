# List of RSS Feeds to monitor (including Tier-0 Primary Sources / "Fontes das Fontes")
RSS_FEEDS = [
    # =========================================================================
    # FONTES PRIMÁRIAS / "FONTES DAS FONTES" (Tier-0 Releases, Reguladores, RI)
    # =========================================================================
    {
        "name": "PR Newswire Brasil (RI)",
        "url": "https://www.prnewswire.com/br/rss/news-releases-list.rss",
        "type": "FATOS",
    },
    {
        "name": "GlobeNewswire Brasil (RI)",
        "url": "https://www.globenewswire.com/RssFeed/country/Brazil/feedTitle/GlobeNewswire%20-%20News%20from%20Brazil",
        "type": "FATOS",
    },
    {
        "name": "Banco Central (BCB)",
        "url": "https://www.bcb.gov.br/api/feed/sitebcb/sitefeeds/noticias",
        "type": "FATOS",
    },
    {
        "name": "Fatos Relevantes & Comunicados (B3)",
        "url": "https://news.google.com/rss/search?q=%22Fato+Relevante%22+OR+%22Comunicado+ao+Mercado%22+OR+%22Aviso+aos+Acionistas%22+when:1d&hl=pt-BR&gl=BR&ceid=BR:pt-419",
        "type": "FATOS",
    },
    {
        "name": "Balanços & Dividendos (B3)",
        "url": "https://news.google.com/rss/search?q=(%221T26%22+OR+%222T26%22+OR+%223T26%22+OR+%224T26%22+OR+%22lucro+l%C3%ADquido%22+OR+%22EBITDA%22+OR+%22dividendos%22+OR+%22JCP%22)+B3+when:1d&hl=pt-BR&gl=BR&ceid=BR:pt-419",
        "type": "FATOS",
    },
    {
        "name": "Reguladores (CADE/ANP/ANEEL/ANATEL/CVM)",
        "url": "https://news.google.com/rss/search?q=(%22CADE%22+OR+%22ANP%22+OR+%22ANEEL%22+OR+%22ANATEL%22+OR+%22CVM%22)+(aprova+OR+autoriza+OR+multa+OR+suspende+OR+leil%C3%A3o+OR+tarifa)+when:1d&hl=pt-BR&gl=BR&ceid=BR:pt-419",
        "type": "FATOS",
    },

    # =========================================================================
    # FATOS (Hard News / Imprensa Primária)
    # =========================================================================
    {
        "name": "Valor Econômico (Empresas)",
        "url": "https://pox.globo.com/rss/valor/empresas/",
        "type": "FATOS",
    },
    {
        "name": "Valor Econômico (Finanças)",
        "url": "https://pox.globo.com/rss/valor/financas/",
        "type": "FATOS",
    },
    {
        "name": "Agência Brasil",
        "url": "https://agenciabrasil.ebc.com.br/rss/economia/feed.xml",
        "type": "FATOS",
    },
    {
        "name": "InfoMoney",
        "url": "https://www.infomoney.com.br/feed/",
        "type": "FATOS",
    },

    # =========================================================================
    # INTERPRETACAO (Relatórios Sell-Side & Análise Especializada)
    # =========================================================================
    {
        "name": "Relatórios Sell-Side (Bancos)",
        "url": "https://news.google.com/rss/search?q=(%22Ita%C3%BA+BBA%22+OR+%22BTG+Pactual%22+OR+%22JPMorgan%22+OR+%22Morgan+Stanley%22+OR+%22Goldman+Sachs%22+OR+%22Bradesco+BBI%22+OR+%22Citi%22)+(%22recomenda%C3%A7%C3%A3o%22+OR+%22pre%C3%A7o-alvo%22+OR+%22compra%22+OR+%22venda%22)+when:1d&hl=pt-BR&gl=BR&ceid=BR:pt-419",
        "type": "INTERPRETACAO",
    },
    {
        "name": "Brazil Journal",
        "url": "https://braziljournal.com/feed/",
        "type": "INTERPRETACAO",
    },
    {
        "name": "NeoFeed",
        "url": "https://neofeed.com.br/feed/",
        "type": "INTERPRETACAO",
    },
    {
        "name": "E-Investidor Estadão",
        "url": "https://einvestidor.estadao.com.br/feed/",
        "type": "INTERPRETACAO",
    },
    {
        "name": "Investing.com (Empresas)",
        "url": "https://br.investing.com/rss/news_356.rss",
        "type": "INTERPRETACAO",
    },
    {
        "name": "Investing.com (Ações)",
        "url": "https://br.investing.com/rss/news_25.rss",
        "type": "INTERPRETACAO",
    },
    {
        "name": "Investing.com",
        "url": "https://br.investing.com/rss/news.rss",
        "type": "INTERPRETACAO",
    },
    {
        "name": "MoneyTimes",
        "url": "https://www.moneytimes.com.br/feed/",
        "type": "INTERPRETACAO",
    },
    {
        "name": "Suno Notícias",
        "url": "https://www.suno.com.br/noticias/feed/",
        "type": "INTERPRETACAO",
    },
    {
        "name": "Exame",
        "url": "https://exame.com/feed/",
        "type": "INTERPRETACAO",
    },

    # =========================================================================
    # PERCEPCAO (Opinion / Social Sentiment)
    # =========================================================================
    {
        "name": "Economista Sincero",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC8cp5_k-W75lR7w_k8gC5EA",
        "type": "PERCEPCAO",
    },
    {
        "name": "Me Poupe!",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCswQx4rDDUxdJdNq1f91sOg",
        "type": "PERCEPCAO",
    },
]
