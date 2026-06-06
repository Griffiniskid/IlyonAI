# Capability audit results

base=http://localhost:3000/api/v1/agent  n=390

| cat | type | n | TOOL% | CHAT | EMPTY | tools fired | verdict |
|---|---|--:|--:|--:|--:|---|---|
| A1 analysis | core | 10 | 40% | 6 | 0 | analyze:4 | 🟡 partial |
| A2 swap | core | 10 | 40% | 1 | 5 | swap:4,shield:2 | 🟡 partial |
| A3 bridge | core | 10 | 10% | 1 | 8 | bridge:1 | ❌ GAP |
| A4 stake | core | 10 | 20% | 1 | 7 | stake:1,swap:1 | ❌ GAP |
| A5 lp/yield | core | 10 | 90% | 0 | 1 | search:9 | ✅ works |
| A6 balance/price | core | 10 | 80% | 2 | 0 | price:5,balance:2,search:1 | ✅ works |
| B1 lending health | action | 10 | 40% | 6 | 0 | search:3,price:1 | 🟡 partial |
| B2 borrow/repay | action | 10 | 80% | 2 | 0 | search:6,compose:2,lp:2 | ✅ works |
| B3 perps/leverage | action | 10 | 20% | 8 | 0 | search:1,price:1 | ❌ GAP |
| B4 options | action | 10 | 20% | 8 | 0 | search:2 | ❌ GAP |
| B5 multi-step compose | action | 10 | 10% | 1 | 8 | search:1 | ❌ GAP |
| B6 cross-chain portfolio | action | 10 | 70% | 2 | 1 | balance:4,allocate:2,compose:2,shield:2 | ✅ works |
| C1 limit orders | action | 10 | 0% | 10 | 0 | - | ❌ GAP |
| C2 stop-loss/TP | action | 10 | 10% | 9 | 0 | balance:1 | ❌ GAP |
| C3 DCA/recurring | action | 10 | 10% | 7 | 2 | allocate:1,compose:1,shield:1 | ❌ GAP |
| C4 conditional/triggers | action | 10 | 30% | 5 | 2 | allocate:1,compose:1,shield:1,search:1 | 🟡 partial |
| C5 routing/MEV | action | 10 | 20% | 3 | 5 | search:2 | ❌ GAP |
| C6 copy-trading | action | 10 | 80% | 2 | 0 | smartmoney:4,search:2,balance:2 | ✅ works |
| D1 portfolio analytics | action | 10 | 50% | 5 | 0 | balance:3,search:1,allocate:1,compose:1 | 🟡 partial |
| D2 pnl/tax | action | 10 | 0% | 10 | 0 | - | ❌ GAP |
| D3 performance/history | action | 10 | 20% | 8 | 0 | balance:2 | ❌ GAP |
| D4 risk/stress | action | 10 | 60% | 4 | 0 | balance:4,allocate:1,compose:1,shield:1 | 🟡 partial |
| E1 price alerts | action | 10 | 0% | 10 | 0 | - | ❌ GAP |
| E2 monitoring | action | 10 | 80% | 2 | 0 | balance:4,search:2,smartmoney:1,lp:1 | ✅ works |
| E3 automation | action | 10 | 60% | 2 | 2 | search:3,balance:1,allocate:1,compose:1 | 🟡 partial |
| E4 watchlist | action | 10 | 0% | 10 | 0 | - | ❌ GAP |
| F1 nfts | action | 10 | 20% | 8 | 0 | price:1,balance:1 | ❌ GAP |
| F2 onchain queries | action | 10 | 10% | 9 | 0 | balance:1 | ❌ GAP |
| F3 charts | action | 10 | 20% | 8 | 0 | price:2 | ❌ GAP |
| F4 governance | action | 10 | 20% | 7 | 1 | search:2 | ❌ GAP |
| F5 airdrops | action | 10 | 30% | 7 | 0 | search:2,balance:1 | 🟡 partial |
| G1 fiat ramp | action | 10 | 10% | 8 | 1 | compose:1,lp:1 | ❌ GAP |
| G2 advice | concept | 10 | 30% | 7 | 0 | search:3 | ok (chat expected) |
| G3 compare | concept | 10 | 50% | 3 | 2 | search:5 | ok (chat expected) |
| H1 clarify | action | 10 | 0% | 6 | 4 | - | ❌ GAP |
| H3 slang/typo | action | 10 | 10% | 9 | 0 | analyze:1 | ❌ GAP |
| H4 multilingual | action | 10 | 0% | 10 | 0 | - | ❌ GAP |
| H5 adversarial/safety | action | 10 | 10% | 2 | 7 | shield:1 | ❌ GAP |
| H6 out-of-scope | concept | 10 | 0% | 10 | 0 | - | ok (chat expected) |

## ❌ GAPS (action categories where the agent rarely fires a tool)

- **C1 limit orders** — only 0% fired a tool
- **D2 pnl/tax** — only 0% fired a tool
- **E1 price alerts** — only 0% fired a tool
- **E4 watchlist** — only 0% fired a tool
- **H1 clarify** — only 0% fired a tool
- **H4 multilingual** — only 0% fired a tool
- **A3 bridge** — only 10% fired a tool
- **B5 multi-step compose** — only 10% fired a tool
- **C2 stop-loss/TP** — only 10% fired a tool
- **C3 DCA/recurring** — only 10% fired a tool
- **F2 onchain queries** — only 10% fired a tool
- **G1 fiat ramp** — only 10% fired a tool
- **H3 slang/typo** — only 10% fired a tool
- **H5 adversarial/safety** — only 10% fired a tool
- **A4 stake** — only 20% fired a tool
- **B3 perps/leverage** — only 20% fired a tool
- **B4 options** — only 20% fired a tool
- **C5 routing/MEV** — only 20% fired a tool
- **D3 performance/history** — only 20% fired a tool
- **F1 nfts** — only 20% fired a tool
- **F3 charts** — only 20% fired a tool
- **F4 governance** — only 20% fired a tool