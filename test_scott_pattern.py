import re

text_problema = "On p.p. 63 & 64 of the OXCART for July, 1964 (Vol. IV, No. 3), I gave in brief the story of the Lindbergh stamp (Scott 147) and a resume of the Colonel's visit to Costa Rica in January, 1928."

# Patrón actual (problemático)
RX_SCOTT_ACTUAL = re.compile(r"\bScott(?:'s)?\s+No\.?\s*([A-Z]?\d+[A-Za-z\-]*)", re.I)

# Patrón mejorado: hace opcional el "No."
RX_SCOTT_MEJORADO = re.compile(r"\bScott(?:'s)?(?:\s+No\.?)?\s*([A-Z]?\d+[A-Za-z\-]*)", re.I)

print("COMPARACION DE PATRONES:")
print("=" * 50)

print(f"\nTexto de prueba:")
print(f"   '{text_problema}'")

print(f"\nPatron actual (requiere 'No.'):")
matches_actual = RX_SCOTT_ACTUAL.findall(text_problema)
print(f"   Encuentra: {matches_actual}")

print(f"\nPatron mejorado (opcional 'No.'):")
matches_mejorado = RX_SCOTT_MEJORADO.findall(text_problema)
print(f"   Encuentra: {matches_mejorado}")

# Probar otros casos comunes
casos_prueba = [
    "Scott No. 123",
    "Scott 147", 
    "Scott's No. 456",
    "Scott's 789",
    "Scott No 234",
    "stamp (Scott 147) and something",
    "Scott C15"
]

print(f"\nCASOS DE PRUEBA:")
print("-" * 30)
for caso in casos_prueba:
    actual = RX_SCOTT_ACTUAL.findall(caso)
    mejorado = RX_SCOTT_MEJORADO.findall(caso)
    print(f"'{caso}':")
    print(f"  Actual: {actual}")
    print(f"  Mejorado: {mejorado}")
    print()