# -*- coding: utf-8 -*-
"""
Direct Real-Time Connector to CVM RAD / Empresas.NET (Fonte Primária / Tier-0 da B3).
Captures Fatos Relevantes, Avisos aos Acionistas (Dividendos/JCP), Releases de Resultados (Dados Econômico-Financeiros),
and Comunicados ao Mercado directly from CVM servers the moment a B3 company files them.
"""
import datetime
import io
import re
import time
import urllib3
import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Deterministic mapping of CVM Code (without leading zeros or hyphens) -> Primary Liquid B3 Ticker
CVM_CODE_TO_TICKER = {
    "1023": "BBAS3",
    "10456": "ALPA4",
    "10880": "SOND3",
    "11070": "WLMM3",
    "1120": "BGIP3",
    "11258": "TELB3",
    "11398": "CRPG3",
    "1155": "BEES3",
    "11592": "UNIP3",
    "1171": "BPAR3",
    "11762": "VULC3",
    "11932": "MYPK3",
    "11975": "AZEV3",
    "11991": "MWET3",
    "1210": "BRSR6",
    "12190": "BOBR3",
    "1228": "BNBR3",
    "12572": "RCSL3",
    "12653": "KLBN11",
    "12696": "SNSY5",
    "12823": "APTI4",
    "1309": "BMIN3",
    "1325": "BMEB3",
    "13285": "JOPA3",
    "13366": "HAGA3",
    "13439": "RSUL4",
    "13471": "PLAS3",
    "13765": "MNPR3",
    "13773": "PTBL3",
    "13781": "SCAR3",
    "13854": "MAPT3",
    "13986": "SUZB3",
    "14109": "RAPT4",
    "14176": "ELPL3",
    "14206": "BSLI3",
    "14311": "CPLE6",
    "14320": "USIM5",
    "14346": "WHRL3",
    "14362": "CEPE3",
    "14443": "SBSP3",
    "14451": "CEBR3",
    "14460": "CYRE3",
    "14524": "CEEB3",
    "14605": "ENMT3",
    "14664": "SHUL4",
    "14826": "PCAR3",
    "14869": "COCE3",
    "1520": "BDLL3",
    "15253": "ENGI11",
    "15342": "ESCE3",
    "15369": "VSPT3",
    "15458": "EPAR3",
    "15539": "NEOE3",
    "1562": "BALM3",
    "15636": "CGAS3",
    "1570": "BAUH4",
    "16101": "GFSA3",
    "16292": "BRFS3",
    "16306": "RSID3",
    "16527": "AESL3",
    "16616": "CEGR3",
    "16632": "DEXP3",
    "16659": "PSSA3",
    "16861": "CASN3",
    "1694": "BMKS3",
    "16985": "EBEN4",
    "16993": "EMAE4",
    "17329": "EGIE3",
    "17450": "RAIL3",
    "17485": "EKTR3",
    "17671": "VIVT3",
    "17892": "STBP3",
    "17973": "COGN3",
    "18139": "CSRN3",
    "18309": "EQPA3",
    "18368": "GEPA3",
    "18376": "ISAE4",
    "18414": "PDTC3",
    "18465": "UGPA3",
    "18597": "DTCY3",
    "18627": "SAPR11",
    "18660": "CPFE3",
    "18708": "PEAB3",
    "18724": "BRAP3",
    "18821": "MOTV3",
    "19100": "CTAX3",
    "19275": "CPFP4",
    "19305": "BIOM3",
    "19330": "TPIS3",
    "19348": "ITUB4",
    "19445": "CSMG3",
    "19453": "ECOR3",
    "19550": "NATU3",
    "19615": "GRND3",
    "19623": "DASA3",
    "19739": "RENT3",
    "19771": "ARTR3",
    "19836": "CSAN3",
    "19879": "LIGT3",
    "19909": "BRML3",
    "19992": "TOTS3",
    "20010": "EQTL3",
    "20028": "VLID3",
    "20036": "AGRO3",
    "20044": "CSUD3",
    "20060": "LUPA3",
    "20087": "EMBJ3",
    "20257": "TAEE11",
    "20338": "MDIA3",
    "20346": "PFRM3",
    "20362": "POSI3",
    "20370": "LPSB3",
    "20435": "TCSA3",
    "20451": "RDNI3",
    "20478": "PDGR3",
    "20494": "IGTA3",
    "20516": "SMTO3",
    "20524": "EVEN3",
    "20532": "SANB11",
    "20540": "CPRE3",
    "20567": "PINE4",
    "20605": "JHSF3",
    "20613": "FRIO3",
    "20621": "FHER3",
    "20630": "FIEI3",
    "20648": "CEED3",
    "20702": "VIVR3",
    "20710": "LOGN3",
    "20729": "PRBC3",
    "20745": "SLCE3",
    "20770": "EZTC3",
    "20788": "MBRF3",
    "20800": "TGMA3",
    "20877": "HBOR3",
    "20915": "MRVE3",
    "20931": "BEEF3",
    "20958": "ABCB4",
    "20982": "MULT3",
    "20990": "AMER3",
    "2100": "CAMB3",
    "21008": "GSHP3",
    "21016": "YDUQ3",
    "21040": "SYNE3",
    "21067": "MDNE3",
    "21091": "DXCO3",
    "21130": "TRIS3",
    "21148": "TEND3",
    "21180": "NEXP3",
    "21237": "ENEV3",
    "21334": "NUTR3",
    "21342": "OSXB3",
    "21350": "DIRR3",
    "21393": "GPAR3",
    "21431": "HYPE3",
    "21440": "VSTE3",
    "21490": "ALUP11",
    "21636": "RNEW3",
    "21733": "CIEL3",
    "21881": "FLRY3",
    "22012": "MILS3",
    "22020": "JSLG3",
    "22055": "AMAR3",
    "22179": "AFLT3",
    "22187": "PRIO3",
    "22349": "AZZA3",
    "22357": "ALOS3",
    "22470": "MGLU3",
    "22497": "QUAL3",
    "22519": "TECN3",
    "22608": "PGMN3",
    "22616": "BPAC11",
    "22675": "HBSA3",
    "22780": "UCAS3",
    "23159": "BBSE3",
    "23221": "SEER3",
    "23248": "ANIM3",
    "23264": "ABEV3",
    "23272": "LOGG3",
    "23310": "CVCB3",
    "23507": "OFSA3",
    "23574": "MEAL3",
    "23590": "WIZC3",
    "23795": "CXSE3",
    "23825": "MOVI3",
    "24058": "AALR3",
    "24112": "AZUL4",
    "24180": "IRBR3",
    "24228": "CAML3",
    "24236": "PRNR3",
    "24260": "SMFT3",
    "2429": "RANI3",
    "24295": "VBBR3",
    "24317": "ZAMP3",
    "2437": "AXIA3",
    "24392": "HAPV3",
    "2453": "CMIG4",
    "24600": "BMGB4",
    "2461": "CLSC3",
    "24627": "BLAU3",
    "24694": "SBFG3",
    "24716": "VAMO3",
    "24805": "VIVA3",
    "24821": "RDOR3",
    "24848": "CEAB3",
    "24902": "MTRE3",
    "24910": "LWSA3",
    "24929": "TIMS3",
    "24953": "ALPK3",
    "24961": "AMBP3",
    "25003": "SIMH3",
    "25038": "LJQQ3",
    "25046": "DMVF3",
    "25062": "LAVV3",
    "25070": "PLPL3",
    "25100": "CURY3",
    "25119": "MELK3",
    "25160": "SEQL3",
    "25186": "GMAT3",
    "25208": "TFCO4",
    "25232": "CASH3",
    "25259": "ENJU3",
    "25275": "AVLL3",
    "25283": "AERI3",
    "25291": "BRAV3",
    "25330": "ALLD3",
    "25372": "ASAI3",
    "25402": "HBRE3",
    "25445": "ESPA3",
    "25453": "INTB3",
    "25461": "TOKY3",
    "25496": "JALL3",
    "25500": "BMOB3",
    "25518": "WEST3",
    "25526": "CSED3",
    "25534": "OPCT3",
    "25550": "ORVR3",
    "25577": "CGOS3",
    "25585": "CMIN3",
    "25658": "AGXY3",
    "25682": "VVEO3",
    "25690": "MATD3",
    "25704": "SOJA3",
    "25712": "GGPS3",
    "25747": "IFCM3",
    "25763": "VITT3",
    "2577": "CESP3",
    "25780": "RECV3",
    "25836": "DOTZ3",
    "25860": "BRBI11",
    "25879": "KRSA3",
    "25887": "ARND3",
    "25895": "WDCN3",
    "25917": "RAIZ4",
    "25950": "TTEN3",
    "25984": "CBAV3",
    "26000": "LAND3",
    "26026": "DESK3",
    "26034": "MLAS3",
    "26050": "FIQE3",
    "26069": "ARML3",
    "26123": "ONCO3",
    "26441": "SRNA3",
    "26620": "AURE3",
    "27057": "VTRU3",
    "27570": "CCTY3",
    "27626": "AZTE3",
    "27650": "RVEE3",
    "27677": "ATED3",
    "27693": "BRST3",
    "27707": "AMOB3",
    "27766": "AUAU3",
    "27910": "OBTC3",
    "3050": "CBEE3",
    "3069": "FESA4",
    "3077": "CEDO3",
    "3190": "REDE3",
    "3204": "EEEL3",
    "3271": "FLCL3",
    "3298": "HBTS5",
    "3654": "MSPA3",
    "3824": "PALF3",
    "3980": "GGBR4",
    "4030": "CSNA3",
    "4081": "CTSA3",
    "4146": "CTKA3",
    "4170": "VALE3",
    "4537": "CGRA3",
    "4693": "ODER3",
    "4723": "CALI3",
    "4820": "BRKM5",
    "5207": "DOHL3",
    "5258": "RADL3",
    "5312": "MNDL3",
    "5380": "EALT3",
    "5410": "WEGE3",
    "5576": "ENER3",
    "5762": "ETER3",
    "5770": "EUCA4",
    "6041": "FIGE3",
    "6173": "TASA3",
    "6211": "FRAS3",
    "6343": "TUPY3",
    "6505": "BHIA3",
    "6629": "HETA3",
    "6700": "HOOT4",
    "701": "BIED3",
    "7510": "ROMI3",
    "7544": "TXRX3",
    "7595": "INEP3",
    "7617": "ITSA4",
    "7811": "JFEN3",
    "7870": "KEPL3",
    "8036": "LIGH3",
    "8133": "LREN3",
    "8192": "LUXM3",
    "8397": "MGEL3",
    "8427": "ESTR3",
    "8451": "POMO4",
    "8575": "LEVE3",
    "8656": "GOAU4",
    "8672": "IGTI11",
    "8753": "MTSA4",
    "8818": "MMAQ3",
    "900179": "CREM3",
    "900189": "PRML3",
    "900288": "AEDU3",
    "900728": "ENAT3",
    "906": "BBDC4",
    "9083": "NORD3",
    "909697": "ACES3",
    "909770": "BHGR3",
    "909788": "BICB3",
    "909796": "BISA3",
    "909846": "CCIM3",
    "910018": "RIPI3",
    "910026": "SFSA3",
    "910067": "TMAR3",
    "910083": "TVIT3",
    "911677": "VIGR3",
    "917594": "PTPA3",
    "917687": "RDCD3",
    "917848": "EMBR3",
    "917927": "MOAR3",
    "917928": "CPFG3",
    "917942": "PETZ3",
    "922": "BAZA3",
    "9342": "PNVL3",
    "9393": "PMAM3",
    "94": "PATI3",
    "9415": "AHEB3",
    "9512": "PETR4",
    "9539": "PTNT3",
    "9954": "RPAD3"
}

ALLOWED_CATEGORIES = (
    "Fato Relevante",
    "Aviso aos Acionistas",
    "Dados Econômico-Financeiros",
    "Comunicado ao Mercado",
)

# Routine administrative filings under Comunicado ao Mercado that do not represent actionable catalysts
IGNORED_SUBJECT_PATTERNS = (
    "valores mobiliarios negociados e detidos",
    "valores mobiliários negociados e detidos",
    "posicao individualizada",
    "posição individualizada",
    "posicao consolidada",
    "posição consolidada",
    "art. 11 da instrucao cvm",
    "art. 11 da resolucao cvm",
    "art. 11 da resolução cvm",
    "calendario de eventos corporativos",
    "calendário de eventos corporativos",
    "mapa final de votacao",
    "mapa sintético de votação",
    "mapa sintetico de votacao",
    "boletim de voto a distancia",
    "boletim de voto a distância",
)


def _normalize_cvm_code(raw_code):
    if not raw_code:
        return ""
    return re.sub(r"[^0-9]", "", str(raw_code)).lstrip("0")


def _parse_brt_datetime(raw_dt_str):
    """
    Parses CVM delivery date string like "20261026 26/10/2026 18:18" or "26/10/2026 18:18"
    into a Unix timestamp (assuming America/Sao_Paulo BRT UTC-3).
    """
    if not raw_dt_str:
        return time.time()
    m = re.search(r"(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2})", raw_dt_str)
    if m:
        dt_part = f"{m.group(1)} {m.group(2)}"
        try:
            brt_tz = datetime.timezone(datetime.timedelta(hours=-3))
            dt = datetime.datetime.strptime(dt_part, "%d/%m/%Y %H:%M").replace(tzinfo=brt_tz)
            return dt.timestamp()
        except Exception:
            pass
    return time.time()


def extract_cvm_pdf_text(download_url, max_chars=3500, max_bytes=4 * 1024 * 1024):
    """
    Downloads the official CVM IPE PDF filing (capped at 4 MB to keep E2.1.Micro RAM tiny)
    and extracts text from the first pages so the AI analyst can read the exact numbers and terms.
    """
    if not download_url:
        return ""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        r = requests.get(download_url, headers=headers, timeout=8, verify=False, stream=True)
        if r.status_code != 200:
            return ""
        chunks = []
        total = 0
        for chunk in r.iter_content(chunk_size=65536):
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                r.close()
                return ""
        content = b"".join(chunks)
        if not content.startswith(b"%PDF"):
            return ""
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(content))
            pages_text = []
            for page in reader.pages[:4]:
                t = page.extract_text() or ""
                if t.strip():
                    pages_text.append(t.strip())
            full_text = "\n".join(pages_text)
            full_text = re.sub(r"\s+", " ", full_text).strip()
            return full_text[:max_chars]
        except Exception:
            return ""
    except Exception:
        return ""


def fetch_recent_cvm_filings(lookback_hours=6):
    """
    Queries CVM RAD (ListarDocumentos) for recent filings by B3-listed companies.
    Returns a list of dicts compatible with monitor.py processing:
      {
        "ticker": "ITUB4",
        "company_name": "ITAU UNIBANCO HOLDING S.A.",
        "category": "Fato Relevante",
        "title": "[CVM Fato Relevante] ITAU UNIBANCO (ITUB4): Aquisição da totalidade das ações...",
        "summary": "...",
        "link": "https://www.rad.cvm.gov.br/ENET/frmDownloadDocumento.aspx?...",
        "timestamp": 1761474600.0,
        "source_name": "CVM (Fato Relevante)",
        "source_type": "FATOS"
      }
    """
    brt_tz = datetime.timezone(datetime.timedelta(hours=-3))
    now_brt = datetime.datetime.now(brt_tz)
    start_brt = now_brt - datetime.timedelta(hours=max(lookback_hours, 2))

    data_de = start_brt.strftime("%d/%m/%Y")
    data_ate = now_brt.strftime("%d/%m/%Y")

    url = "https://www.rad.cvm.gov.br/ENET/frmConsultaExternaCVM.aspx/ListarDocumentos"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Content-Type": "application/json; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
    }
    # Categories:
    # IPE_4_-1_-1 = Fato Relevante
    # IPE_1_-1_-1 = Aviso aos Acionistas (Dividendos / JCP / Subscricao)
    # IPE_6_-1_-1 = Dados Economico-Financeiros (Release de Resultados / Guidance)
    # IPE_7_-1_-1 = Comunicado ao Mercado
    payload = {
        "dataDe": data_de,
        "dataAte": data_ate,
        "empresa": "",
        "setorAtividade": "-1",
        "categoriaEmissor": "-1",
        "situacaoEmissor": "-1",
        "tipoParticipante": "-1",
        "dataReferencia": "",
        "categoria": "IPE_4_-1_-1,IPE_1_-1_-1,IPE_6_-1_-1,IPE_7_-1_-1",
        "periodo": "2",
        "horaIni": "",
        "horaFim": "",
        "palavraChave": "",
        "ultimaDtRef": "false",
        "tipoEmpresa": "0",
        "token": "",
        "versaoCaptcha": "",
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=12, verify=False)
        if resp.status_code != 200:
            return []
        dados = (resp.json().get("d") or {}).get("dados") or ""
        if not dados:
            return []
    except Exception as e:
        print(f"CVM RAD fetch error: {e}")
        return []

    cutoff_ts = now_brt.timestamp() - (lookback_hours * 3600)
    filings = []

    rows = [r for r in dados.split("&*") if r.strip()]
    for row in rows:
        raw_cols = row.split("$&")
        if len(raw_cols) < 8:
            continue
        cols = [re.sub(r"<[^>]+>", "", c).strip() for c in raw_cols]
        cvm_code_raw = cols[0]
        company_name = cols[1]
        category = cols[2]
        doc_subtype = cols[3] if cols[3] != "-" else ""
        subject = cols[4].rstrip("- ").strip() if cols[4] != "-" else ""
        ref_date = re.sub(r"^\d{8}\s*", "", cols[5]).strip()
        delivery_raw = cols[6]
        status = cols[7]

        if status.lower() != "ativo":
            continue
        if category not in ALLOWED_CATEGORIES:
            continue

        norm_code = _normalize_cvm_code(cvm_code_raw)
        ticker = CVM_CODE_TO_TICKER.get(norm_code)
        if not ticker:
            continue

        delivery_ts = _parse_brt_datetime(delivery_raw)
        if delivery_ts < cutoff_ts:
            continue

        # Filter out noisy routine monthly filings in Comunicado ao Mercado
        combined_lower = f"{category} {doc_subtype} {subject}".lower()
        if any(pat in combined_lower for pat in IGNORED_SUBJECT_PATTERNS):
            continue

        action_html = raw_cols[10] if len(raw_cols) > 10 else raw_cols[-1]
        dl_match = re.search(
            r"OpenDownloadDocumentos\('([^']+)',\s*'([^']+)',\s*'([^']+)',\s*'([^']+)'\)",
            action_html,
        )
        if dl_match:
            num_seq, num_ver, num_prot, desc_tipo = dl_match.groups()
            doc_url = (
                f"https://www.rad.cvm.gov.br/ENET/frmDownloadDocumento.aspx"
                f"?Tela=ext&numSequencia={num_seq}&numVersao={num_ver}"
                f"&numProtocolo={num_prot}&descTipo={desc_tipo}&CodigoInstituicao=1"
            )
        else:
            doc_url = f"https://www.rad.cvm.gov.br/ENET/frmConsultaExternaCVM.aspx?codigoCVM={norm_code}&ts={int(delivery_ts)}"

        delivery_display = re.sub(r"^\d{8}\s*", "", delivery_raw).strip()
        headline_detail = subject or doc_subtype or f"Ref. {ref_date}"
        title = f"[CVM {category}] {company_name} ({ticker}): {headline_detail}"
        summary = (
            f"Documento oficial protocolado na CVM/B3 (Sistema Empresas.NET) em {delivery_display} BRT. "
            f"Empresa: {company_name} ({ticker}) | Categoria: {category}"
            + (f" ({doc_subtype})" if doc_subtype else "")
            + (f" | Assunto: {subject}" if subject else "")
            + (f" | Data de Referência: {ref_date}" if ref_date and ref_date != "-" else "")
        )

        filings.append(
            {
                "ticker": ticker,
                "company_name": company_name,
                "category": category,
                "title": title,
                "summary": summary,
                "link": doc_url,
                "timestamp": delivery_ts,
                "source_name": f"CVM ({category})",
                "source_type": "FATOS",
            }
        )

    filings.sort(key=lambda x: x["timestamp"])
    return filings
