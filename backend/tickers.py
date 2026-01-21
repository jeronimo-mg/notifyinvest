import json

# List of major B3 companies (IBOVESPA + Others)
# We use a static list to avoid scraping failures and API keys.
# This covers >90% of the volume and news interest.
B3_TICKERS = [
    "ABEV3", "ALPA4", "ALSO3", "ARZZ3", "ASAI3", "AZUL4", "B3SA3", "BBAS3", "BBDC3", "BBDC4",
    "BBSE3", "BEEF3", "BPAC11", "BPAN4", "BRAP4", "BRFS3", "BRKM5", "BROT3", "CASH3", "CCRO3",
    "CIEL3", "CMIG4", "CMIN3", "COGN3", "CPFE3", "CPLE6", "CRFB3", "CSAN3", "CSNA3", "CVCB3",
    "CYRE3", "DXCO3", "ECOR3", "EGIE3", "ELET3", "ELET6", "EMBR3", "ENBR3", "ENEV3", "ENGI11",
    "EQTL3", "EZTC3", "FLRY3", "GGBR4", "GOAU4", "GOLL4", "HAPV3", "HYPE3", "IGTI11", "IRBR3",
    "ITSA4", "ITUB4", "JBSS3", "KLBN11", "LREN3", "LWSA3", "MGLU3", "MRFG3", "MRVE3", "MULT3",
    "NTCO3", "PCAR3", "PETR3", "PETR4", "PETZ3", "POSI3", "PRIO3", "QUAL3", "RADL3", "RAIL3",
    "RAIZ4", "RDOR3", "RENT3", "RRRP3", "SANB11", "SBSP3", "SLCE3", "SMTO3", "SOMA3", "SUZB3",
    "TAEE11", "TIMS3", "TOTS3", "UGPA3", "USIM5", "VALE3", "VBBR3", "VIIA3", "VIVT3", "WEGE3",
    "YDUQ3"
]

def get_all_tickers():
    """Returns a list of B3 tickers."""
    return B3_TICKERS

def get_ticker_names():
    """
    Returns a dictionary mapping Ticker -> Common Name/Keywords.
    Used for fuzzy matching in news.
    """
    # Simply using the ticker name as a keyword for now, 
    # but ideally we would map "PETR4" -> ["Petrobras", "Petrolileo Brasileiro"]
    # We will expand this map for better 'Matcher' quality.
    mapping = {
        "PETR3": ["Petrobras"], "PETR4": ["Petrobras"],
        "VALE3": ["Vale"],
        "ITUB4": ["Itaú", "Itau Unibanco"],
        "BBDC4": ["Bradesco"],
        "ABEV3": ["Ambev"],
        "BBAS3": ["Banco do Brasil"],
        "WEGE3": ["WEG"],
        "MGLU3": ["Magalu", "Magazine Luiza"],
        "VIIA3": ["Via", "Casas Bahia"],
        "JBSS3": ["JBS"],
        "SUZB3": ["Suzano"],
        "GGBR4": ["Gerdau"],
        "CSNA3": ["Siderúrgica Nacional", "CSN"],
        "ITSA4": ["Itaúsa"],
        "HAPV3": ["Hapvida"],
        "EQTL3": ["Equatorial"],
        "RENT3": ["Localiza"],
        "RDOR3": ["Rede D'Or"],
        "LREN3": ["Lojas Renner", "Renner"],
        "B3SA3": ["B3", "Bolsa"],
    }
    return mapping
