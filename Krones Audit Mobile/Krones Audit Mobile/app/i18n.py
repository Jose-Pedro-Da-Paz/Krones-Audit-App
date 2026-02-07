# app/i18n.py
from typing import Dict

def get_title(title_map: Dict[str, str], lang: str) -> str:
    """Retorna o título no idioma solicitado, com fallback para qualquer disponível."""
    if not title_map:
        return ""
    if lang in title_map and title_map[lang]:
        return title_map[lang]
    # fallback: primeira chave disponível
    for _, v in title_map.items():
        if v:
            return v
    return ""