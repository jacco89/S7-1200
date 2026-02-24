# PLC Tester

Profesjonalne narzędzie diagnostyczne do testowania komunikacji z PLC Siemens S7-1200/1500.  
Obsługuje dwa protokoły w osobnych zakładkach: **S7Comm (Snap7)** i **OPC UA (AsyncUA)**.

![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue)
![PySide6](https://img.shields.io/badge/GUI-PySide6-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## Instalacja

### Wymagania wstępne
- Python 3.11 lub nowszy
- [uv](https://docs.astral.sh/uv/) – menedżer zależności

### Kroki

```bash
# Klonuj repozytorium
git clone <repo-url>
cd plc_tester

# Zainstaluj zależności
uv sync

# Uruchom aplikację
uv run plc-tester
```

### Tryb developerski

```bash
# Zainstaluj z zależnościami dev
uv sync --dev

# Lint
uv run ruff check src/ tests/

# Testy
uv run pytest tests/ -v
```

---

## ⚠️ Konfiguracja krytyczna – S7-1200/1500 (S7Comm)

Aby komunikacja przez protokół S7Comm (Snap7) działała prawidłowo, **musisz** dokonać
dwóch zmian w TIA Portal:

### 1. Włącz dostęp PUT/GET

1. Otwórz projekt w **TIA Portal**.
2. Przejdź do **Device configuration** → kliknij na CPU.
3. W panelu **Properties** przejdź do:  
   `General` → `Protection & Security` → `Connection mechanisms`
4. Zaznacz opcję: **☑ Permit access with PUT/GET communication from remote partner**.
5. Skompiluj i wgraj program do PLC.

### 2. Wyłącz Optimized block access

Dla **każdego bloku danych (DB)**, który chcesz odczytywać:

1. Kliknij prawym przyciskiem na DB → **Properties**.
2. W zakładce **Attributes** odznacz:  
   **☐ Optimized block access**
3. Skompiluj i wgraj ponownie.

> **Uwaga:** Bez tych zmian Snap7 zwróci błąd dostępu lub nieprawidłowe dane.

---

## 🌐 Konfiguracja OPC UA – S7-1200/1500

### Aktywacja serwera OPC UA w CPU

1. Otwórz projekt w **TIA Portal** (V15+).
2. Przejdź do **Device configuration** → kliknij na CPU.
3. W panelu **Properties** przejdź do:  
   `General` → `OPC UA` → `Server`
4. Zaznacz: **☑ Activate OPC UA Server**.
5. Skonfiguruj **port** (domyślnie `4840`).
6. W sekcji **Security**:
   - Ustaw **Security Policy** (np. `Basic256Sha256`).
   - Dodaj użytkownika w zakładce **User authentication** (opcjonalnie).
7. W sekcji **Server interfaces** upewnij się, że interesujące zmienne są
   **dostępne** (wyeksportowane do przestrzeni nazw OPC UA).
8. Skompiluj i wgraj program do PLC.

### URL połączenia

```
opc.tcp://<IP_PLC>:4840
```

### Przykładowe Node ID

```
ns=3;s="DataBlock"."SensorValue"
ns=3;s="DB_Monitoring"."Temperature"
```

---

## Funkcje aplikacji

| Funkcja                 | S7Comm (Snap7)            | OPC UA (AsyncUA)           |
|-------------------------|---------------------------|----------------------------|
| Połączenie              | IP + Rack + Slot          | URL + opcjonalnie User/Pass|
| Zmienne                 | 10 wierszy, typ + adres   | 10 wierszy, Node ID        |
| Odczyt cykliczny        | ✅ 250 ms – 5000 ms       | ✅ 250 ms – 5000 ms        |
| Auto-reconnect          | ✅ co 5 s                 | ✅ co 5 s                  |
| Zapis konfiguracji      | ✅ config.json             | ✅ config.json              |
| Logi w czasie rzeczywistym | ✅                      | ✅                         |

---

## Struktura projektu

```
plc_tester/
├── .github/workflows/ci.yml
├── src/
│   └── plc_tester/
│       ├── __init__.py
│       ├── main.py
│       ├── core/
│       │   ├── s7_client.py
│       │   ├── opcua_client.py
│       │   ├── parser.py
│       │   └── config_manager.py
│       └── ui/
│           ├── main_window.py
│           ├── s7_tab.py
│           └── opcua_tab.py
├── tests/
│   └── test_parser.py
├── pyproject.toml
└── README.md
```

---

## Licencja

MIT
