# PROJECT REVIEW & TODO LIST
# Moon Dev's Hyperliquid Data Layer V2 Bot
# Reviewed: 2026-03-19

## CRITICAL FINDING: Moon Dev API Dependency

The `MOONDEV_API_KEY` is **REQUIRED** for ~85% of the bot functionality.
All data endpoints route through `https://api.moondev.com`.

Without it, only the SwarmAgent (AI queries via OpenRouter) and
direct Hyperliquid user position queries work.

## Bot Working Status

| Component | File | Lines | Status | Blocker |
|---|---|---|---|---|
| Core Data Client | `api.py` | 1,695 | BLOCKED | Needs MOONDEV_API_KEY |
| AI Swarm Agent | `swarm_agent.py` | 192 | WORKS | Needs OPENROUTER_API_KEY only |
| Director Agent | `director_agent_ai2.py` | 567 | PARTIAL | Needs both API keys |
| BTC Liquidation Monitor | `btc_near_liquidation.py` | 319 | BLOCKED | Needs MOONDEV_API_KEY |
| Multi-Exchange Liq Stream | `liquidation_stream.py` | 431 | BLOCKED | Needs MOONDEV_API_KEY |
| CVD Scanner (Multi) | `1_cvd_scanner.py` | 584 | BLOCKED | Needs MOONDEV_API_KEY |
| CVD Scanner (BTC) | `2_cvd_scanner.py` | 742 | BLOCKED | Needs MOONDEV_API_KEY |
| API Health Monitor | `api._monitor.py` | 445 | BLOCKED | Needs MOONDEV_API_KEY + Telegram |

**Overall: ~15-20% functional without Moon Dev API key**

## Required API Keys

| Key | Service | Required? | Cost |
|---|---|---|---|
| `MOONDEV_API_KEY` | Moon Dev data layer | YES (core) | Paid/Freemium |
| `OPENROUTER_API_KEY` | Multi-model AI access | YES (for AI) | Pay-per-token |
| `TELEGRAM_BOT_TOKEN` | Alert notifications | OPTIONAL | Free |
| `TELEGRAM_CHAT_ID` | Alert recipient | OPTIONAL | Free |

## Alternative Data Sources (to replace Moon Dev API)

| Moon Dev Endpoint | Alternative | Difficulty |
|---|---|---|
| Liquidations (multi-exchange) | Coinglass API or direct exchange APIs | Medium-High |
| Positions / Whales | Hyperliquid direct API + custom aggregation | High |
| HLP Sentiment (z-scores) | Custom calc from HLP vault on-chain data | High |
| Smart Money Rankings | Custom tracker from Hyperliquid on-chain | Very High |
| Order Flow / CVD | Hyperliquid WebSocket + custom aggregation | Medium |
| Market Data (prices, candles) | Hyperliquid API directly or CCXT library | Low |

## TODO LIST

### Phase 1: Immediate Setup
- [ ] Create `.env` file from `.env.example`
- [ ] Get OpenRouter API key at https://openrouter.ai
- [ ] Install dependencies: `pip install requests python-dotenv openai rich termcolor`
- [ ] Create `requirements.txt` (currently missing)
- [ ] Test `swarm_agent.py` standalone

### Phase 2: Decide Data Source Strategy
- [ ] Option A: Get Moon Dev API key (check https://moondev.com for free tier)
- [ ] Option B: Build alternative data layer (Hyperliquid direct + Coinglass)
- [ ] Option C: Use Claude AI to build custom data aggregation

### Phase 3: Replace Moon Dev API (if Option B/C)
- [ ] Create `data_provider.py` abstraction layer
- [ ] Implement Hyperliquid direct API: prices, positions, orderbook, candles
- [ ] Implement liquidation tracking via WebSocket or Coinglass
- [ ] Implement HLP sentiment from raw vault data
- [ ] Implement order flow / CVD from tick WebSocket
- [ ] Wire scanners to new data provider

### Phase 4: AI Agent Improvements
- [ ] Add Claude Opus 4.6 directly via Anthropic API (better than OpenRouter)
- [ ] Replace Director Agent's Grok 4 with Claude for superior reasoning
- [ ] Add persistent memory/context to agents
- [ ] Add automated trading signal generation
- [ ] Build backtesting for ideas from `ideas.md`

### Phase 5: Production Readiness
- [ ] Set up Telegram bot for alerts
- [ ] Add data persistence (CSV/SQLite)
- [ ] Add reconnection logic and error recovery
- [ ] Add scheduling (cron/systemd) for monitors
- [ ] Add position sizing and risk management

## AI Swarm Architecture

**Current:** Custom parallel query system (NOT OpenAI Swarm or CrewAI)
- 6 models queried via OpenRouter in parallel using ThreadPoolExecutor
- Director Agent (Grok 4 Fast) orchestrates API calls
- SwarmAgent provides multi-perspective analysis

**Recommended Changes:**
1. Use Claude Opus 4.6 directly via Anthropic API as primary analyst
2. Keep OpenRouter Swarm for multi-perspective confirmation
3. Add tool use / function calling for structured trading output
4. Add persistent conversation memory for context across sessions
