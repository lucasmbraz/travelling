"""Nomes amigáveis para códigos IATA mais comuns (o resto aparece só o código)."""

AIRPORTS = {
    "BEL": "Belém", "MCZ": "Maceió", "REC": "Recife", "FOR": "Fortaleza", "SSA": "Salvador",
    "NAT": "Natal", "JPA": "João Pessoa", "AJU": "Aracaju", "SLZ": "São Luís", "THE": "Teresina",
    "MAO": "Manaus", "STM": "Santarém", "MAB": "Marabá", "MCP": "Macapá", "PMW": "Palmas",
    "BVB": "Boa Vista", "PVH": "Porto Velho", "RBR": "Rio Branco", "BSB": "Brasília",
    "GYN": "Goiânia", "CGB": "Cuiabá", "CGR": "Campo Grande", "CNF": "Belo Horizonte",
    "GRU": "São Paulo (Guarulhos)", "CGH": "São Paulo (Congonhas)", "VCP": "Campinas",
    "SAO": "São Paulo", "GIG": "Rio de Janeiro (Galeão)", "SDU": "Rio de Janeiro (Santos Dumont)",
    "RIO": "Rio de Janeiro", "VIX": "Vitória", "CWB": "Curitiba", "FLN": "Florianópolis",
    "POA": "Porto Alegre", "IGU": "Foz do Iguaçu", "NVT": "Navegantes", "BPS": "Porto Seguro",
    "IOS": "Ilhéus", "FEN": "Fernando de Noronha", "JDO": "Juazeiro do Norte", "PNZ": "Petrolina",
    "IMP": "Imperatriz", "JJD": "Jericoacoara", "CPV": "Campina Grande",
    "LIM": "Lima (Peru)", "CUZ": "Cusco (Peru)", "BOG": "Bogotá", "MDE": "Medellín",
    "CTG": "Cartagena", "EZE": "Buenos Aires", "AEP": "Buenos Aires (Aeroparque)", "BUE": "Buenos Aires",
    "SCL": "Santiago", "MVD": "Montevidéu", "ASU": "Assunção", "UIO": "Quito", "PTY": "Cidade do Panamá",
    "CAY": "Caiena (Guiana Francesa)", "PBM": "Paramaribo", "GEO": "Georgetown",
    "MIA": "Miami", "FLL": "Fort Lauderdale", "MCO": "Orlando", "JFK": "Nova York", "NYC": "Nova York",
    "LIS": "Lisboa", "OPO": "Porto", "MAD": "Madri", "PAR": "Paris", "CDG": "Paris",
    "CUN": "Cancún", "PUJ": "Punta Cana", "HAV": "Havana",
}


def city(code: str) -> str:
    return AIRPORTS.get(code.upper(), code.upper())


def label(code: str) -> str:
    name = AIRPORTS.get(code.upper())
    return f"{name} ({code.upper()})" if name else code.upper()
