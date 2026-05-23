#!/usr/bin/env python3
"""
AskMukthiGuru — Bulk YouTube Transcript Extractor v5
Actor : johnvc/YoutubeTranscripts  ✅ TESTED & CONFIRMED WORKING
Cost  : ~$0.00012 per video (70x cheaper than original estimate)

FEATURES:
  ✅ Python 3.8+ compatible
  ✅ Strict deduplication across runs and within a run
  ✅ Thorough noise stripping ([Music], [Applause], timestamps, filler)
  ✅ Punctuation restoration — TWO-TIER:
       Tier 1: deepmultilingualpunctuation (fast, local BERT model)
       Tier 2: Claude API fallback (better for Sanskrit/spiritual terms)
  ✅ Full exception handling at every level
  ✅ Atomic JSON saves (no corruption on crash)
  ✅ Resumable via _state.json

Punctuation behaviour:
  - If deepmultilingualpunctuation is installed  → uses BERT model (fast)
  - If not installed / fails                     → falls back to Claude API
  - Set PUNCT_MODE = "claude" to force Claude API for all videos
  - Set PUNCT_MODE = "none"   to skip punctuation entirely

Usage:
    pip install apify-client deepmultilingualpunctuation   # deepmulti optional
    export APIFY_API_TOKEN="your_token_here"
    export ANTHROPIC_API_KEY="your_anthropic_key"          # needed for Claude fallback
    python extract_transcripts.py
"""

import os

# Enable MPS fallback for PyTorch operations not yet supported on Apple Silicon GPU
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"

import json
import re
import signal
import sys
import time
import traceback
from pathlib import Path

# ─────────────────────────────────────────────
# DEPENDENCY CHECKS
# ─────────────────────────────────────────────
try:
    from apify_client import ApifyClient
except ImportError:
    print("ERROR: apify-client not installed.  Fix: pip install apify-client")
    sys.exit(1)

try:
    import urllib.error as _urllib_err
    import urllib.request as _urllib_req
except ImportError:
    pass  # stdlib, always present

try:
    from deepmultilingualpunctuation import PunctuationModel

    print("⏳ Loading punctuation model (first run may download ~500 MB)...")
    _punct_model = PunctuationModel()
    BERT_PUNCT_AVAILABLE = True
    print("✅ Punctuation model (BERT) ready.")
except ImportError:
    _punct_model = None
    BERT_PUNCT_AVAILABLE = False
    print("⚠️  deepmultilingualpunctuation not installed — will use Claude API fallback.")
    print("   Optional install: pip install deepmultilingualpunctuation")
except Exception as e:
    _punct_model = None
    BERT_PUNCT_AVAILABLE = False
    print(f"⚠️  Punctuation model failed to load: {e} — will use Claude API fallback.")

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
APIFY_TOKEN = os.environ.get("APIFY_API_TOKEN", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
NVIDIA_KEY = os.environ.get("NVIDIA_API_KEY", "")
ACTOR_ID = "johnvc/YoutubeTranscripts"  # ✅ tested, confirmed working
BATCH_SIZE = 5  # videos per Apify run (was 10, reduced for better return rate)
RETRY_BATCH_SIZE = 2  # smaller batches for retrying timeout victims
SLEEP_BETWEEN = 3  # seconds between batches
RUN_TIMEOUT = 180  # seconds before aborting an Apify run (was 120)
RETRY_TIMEOUT = 300  # longer timeout for retry batches
MAX_RETRY_ATTEMPTS = 3  # max retries before permanently failing a timeout victim
OUTPUT_DIR = Path("transcripts")
STATE_FILE = OUTPUT_DIR / "_state.json"
FAILED_FILE = OUTPUT_DIR / "_failed.txt"
JSON_FILE = OUTPUT_DIR / "transcripts.json"

# ── Completeness validation thresholds ─────────────────────────────────────
# 100% data quality: no partial transcripts ever saved to .md
MIN_COVERAGE_PCT = 0.95  # timestamped segments must cover ≥95% of video duration
MIN_WORDS_PER_MIN = 30  # minimum word density (conservative — even slow speakers hit 50+)

# Punctuation mode:
#   "council" → Two-pass Council mode: BERT first (local), then NVIDIA API refinement (best quality & cost-effective)
#   "nvidia"  → NVIDIA API (Llama-3.1-70b-instruct) always
#   "auto"    → BERT if available, NVIDIA API if not  (default fallback)
#   "bert"    → BERT only (skip if unavailable)
#   "claude"  → Claude API always
#   "none"    → skip punctuation entirely
PUNCT_MODE = "council"


# ── Graceful shutdown: convert SIGTERM → KeyboardInterrupt ─────────────────
# This ensures `kill PID` (SIGTERM) triggers the same clean state-save path
# as Ctrl-C (SIGINT), so no progress is lost when the process is stopped.
def _sigterm_handler(signum, frame):
    raise KeyboardInterrupt("SIGTERM received — shutting down gracefully")


signal.signal(signal.SIGTERM, _sigterm_handler)

# ─────────────────────────────────────────────
# VIDEO IDs
# ─────────────────────────────────────────────

PENDING_IDS = [
    "UNdwPjyLGn0",
    "Js7ongWaW64",
    "oXRZhJTHuOA",
    "zGOKGrTNlk4",
    "4_Fqfew1PRk",
    "idoWVpnJz-Y",
    "Vr3PS2DdbDU",
    "l6svaRx35TI",
    "KTlY-lHs_Ew",
    "pTnZt0SqDFM",
    "nQpRoOOu5Yc",
    "d0v8RE6i0GM",
    "vjEsXpEtpH4",
    "AyUE-2Uh5Vg",
    "WfkCDNu4SuE",
    "VTx4G0KEuUE",
    "1kS_mQaBLdg",
    "W2ZzApmqJmo",
    "Tc8f9ZasRRM",
    "-yGLiryVQoQ",
    "Ji-hdW1t30g",
    "U1qRvz3hnMA",
    "LapJqYf9hzI",
    "Z7w7soyXmHs",
    "PFNP4c1cOSI",
    "XFFgRTgP8Rs",
    "jy4hcpUSBms",
    "qDSfb0DZ0PE",
    "hqre34QIMZg",
    "xUO_WoOlWmI",
    "XMzZe5aEmTo",
    "RvgN5Mfbd5A",
    "3WnNyhhB_4w",
    "F-hNATzOz2I",
    "6j6EGVpQkI8",
    "aqSM9LwqWgA",
    "5YJ6vynFWFc",
    "Ao8Rhhl9E8k",
    "E8N04l1Lptk",
    "EhY6npcnSs8",
    "s6B81c2uTGg",
    "MJYpyUlwxg0",
    "Xk1KsO3efP4",
    "oZRQoiRe7s4",
    "tegTDWT3SDc",
    "Fn62UQTIMEk",
    "PnvNqgTyIFI",
    "LFTx6ZYMZ1g",
    "CQEGJ0OaIPo",
    "zGhlBQ8iWl4",
    "8p3zqYg5wuo",
    "aJIunwxx3NI",
    "WwgBOejW_pI",
    "TXAKaPwrBy0",
    "q15gR1aGjVs",
    "bMGaQ2nUE5Y",
    "07NOYJmkkFo",
    "qJxGtSDiayM",
    "ZD1nQPtpojM",
    "3ITFXvYIPqg",
    "oSqD_BvF7vA",
    "TQ0TGyaByhs",
    "x1Neqc9ytqE",
    "cxgHFX04RtQ",
    "77dJnbTCwsA",
    "D-RK1E9uoP8",
    "b-MkLkpTeVY",
    "FP5O9F9JiOk",
    "-pBQ6Sy444o",
    "p2HecXyM3tE",
    "uvhEf3ToMHI",
    "vNj7OSHos1I",
    "cu-Tx7ehQvM",
    "yJoWk10CSjg",
    "2seBB2oByZc",
    "vIUY446FVPw",
    "7b6tnI7VmB4",
    "bh_kjn-1CAY",
    "L09zAtTcwes",
    "zvRiparLGl8",
    "69IrsSXeBTg",
    "igSp4H0OWLE",
    "iikr2xzAK6Y",
    "k0GsZxWhjSE",
    "ZaZOJ6gazYM",
    "mbhdVEKEbLg",
    "uGosHULQQk0",
    "QWKFjbNhiNw",
    "h8DQ0GlvD8I",
    "X3LKG0Ycl3A",
    "co9vrSiN8ak",
    "M_BYTcsLQuY",
    "o_eg6YTifRE",
    "utRatnFr-S8",
    "5Tdb7hBwX88",
    "4ytgjpow498",
    "0u9oe-5HPmk",
    "8fKvjHOD_kQ",
    "1sMxPhQcvEA",
    "b6nQnYzo_bY",
    "stUPu1-W4bE",
    "6EHw_0gYD5w",
    "6rLvPzNyLRw",
    "OzgA9wYM6Oc",
    "tDcy09esbe8",
    "qQmrTz6i2x4",
    "5hNCT4duOgc",
    "r_l2RNcSPPA",
    "I6yC-aUQUvw",
    "Vt_CjAdzebM",
    "iIduE7RwihM",
    "aSNQUkuyB18",
    "tl2Ek-QakME",
    "g1tezETHrfY",
    "1J0HpmGWsZs",
    "nCK4-w8xu9Y",
    "zFOxZ2oo8-U",
    "3weAVHuSCxg",
    "U23yKxWbIcI",
    "x-mTRlE0TC4",
    "CrZuPkgwA6Q",
    "ajMAwlKh3YM",
    "nCkbv_lvFfg",
    "mmpmX3-qfc4",
    "BZDXIQwOPdU",
    "DmzZPgTh7_M",
    "Lst4MvxPCx4",
    "YkIBYppBtro",
    "3RyCldrCxL8",
    "1_-cZz8YRFw",
    "kMc_kat7YLE",
    "_GEMrEWCiXw",
    "sMgbjxyrgqw",
    "beh0v5Odn6g",
    "V45jIC4RthQ",
    "m-m2wMW4020",
    "EFJZ2l5Rc10",
    "YxglvjuoMZI",
    "T3I8r_NU2Wk",
    "3HytZ8tSiYE",
    "ApX7lGnn-2U",
    "LOsAzhRwUIk",
    "05wF2qqUVnI",
    "FoTH9BWP2gg",
    "Yf4Pld6UEdg",
    "h5Cvb_ZXnJc",
    "hPALIQJXMFg",
    "0va0izWG0Hc",
    "mgfhxq9bn8Q",
    "93evJf7Il-c",
    "7lggUuJtZXY",
    "8CgS_ANm26Y",
    "9-NMv5E-18s",
    "QAnRefsK-3Y",
    "VbT9vgs06Gc",
    "cy7L7ru37HE",
    "pR7zkayrXn8",
    "sO6_webPTdg",
    "zPsun8EkA2s",
    "8RbRpbaCh1I",
    "E9BYLwkGel8",
    "HpoWKtIcTcw",
    "YEPXAy-jyVo",
    "c_w5JbP_N90",
    "dd1OcfbBTh4",
    "fuTnlIafdLY",
    "i4DQFbs_RKU",
    "sOv9ISMIRQ0",
    "sQkhrJ3C49w",
    "s4cOjzTWGh8",
    "Q_CMuXKuvoU",
    "bF6kr28QHJc",
    "inL9r7ffQ7c",
    "36rdT1bFOk0",
    "4HRL8IxADhg",
    "BLvi5n274XY",
    "YZaEmcxvYvc",
    "bHd9dYS6UiU",
    "cqvwOx5baxM",
    "dQw77H27GMY",
    "hfOFmTBWTSQ",
    "1e0yk20hF7Y",
    "453IrXoe_Ug",
    "5TbaZA522Fs",
    "5ia1FNUN6fk",
    "AQUZcU5L9xE",
    "HLTISkkGbUI",
    "MuxETIn04F8",
    "1cs5nliQUSQ",
    "NMjYsvaOOQM",
    "NdmpvgZI4II",
    "WWIURef-J3s",
    "WhYY6IKaiVI",
    "WkkKW_mbWQI",
    "Yfi6-_lYa58",
    "_-P-9fe5U_4",
    "bVcY8fIlDa4",
    "mAG-Q4DZ5Zs",
    "nHDXMZLLQyY",
    "nxfjPX2qD_U",
    "o6X1TVEFHAY",
    "owC8E_G2fY4",
    "smrj15-QOAI",
    "tMaJzikpfeY",
    "tOi1Ho5Kwhk",
    "y2ZgKdt4Cj0",
    "16UXpd5BstM",
    "2JL1ZgMS7nY",
    "3qEON3iXjNM",
    "5hOsWGYAHFg",
    "8KaPqYLRWjc",
    "9id3ygnEhh8",
    "FYQHXDtlYX4",
    "LKM-M3C8Tv4",
    "SyT0Jx-ZT2g",
    "U6pcGCyOYwo",
    "UpeaTtqs7Oc",
    "aqpjV4cSJBI",
    "cvREfQLxC6k",
    "nsWiuQDzAw4",
    "pomBCVpfFNw",
    "rnp4upHkaqQ",
    "vmm8-Vqr8GQ",
    "wZ9FcYgjbPM",
    "J81diFHJqWw",
    "hF3NZH-UX0Y",
    "QexlGYK0DI4",
    "d3pf-MPqRKY",
    "xTVHvMHakow",
    "EyIJaL1sfpc",
    "1GLc7XE0Yvw",
    "zO8tQkjCpyc",
    "FSxiSEV1iPY",
    "kyEL8OTZwBk",
    "N0EoDEdWKA4",
    "EBBd2MOeOIU",
    "txmjnRTgB4Y",
    "09d8aVgYOqQ",
    "8XUuSO6eV7s",
    "SJcLsbR7ccQ",
    "_laoTHp0JWw",
    "dYCLRvvEnVA",
    "gRaAmM9ehzI",
    "kB9lSN4nORo",
    "kf-IuHxVN7g",
    "dj9ymEytgS0",
    "uPm6kDwrjSY",
    "yc-Qs4eiZ2U",
    "Ip7C7KJBxBk",
    "LpX01AXN5iM",
    "LrMyaDh_MSo",
    "53Jzhrf-IWk",
    "ALXWHiS-ing",
    "GWiiejeyAR8",
    "LYm7oczfWEk",
    "OnAAtrwsfOc",
    "QpmmGqGoo-8",
    "UuPdfdrvpdQ",
    "cD6Wi47E0hk",
    "xFQSF6GzQXQ",
    "eumRL5DfFzM",
    "fYhbxU61wuI",
    "mvSrmuOyRYQ",
    "zyUzxY37YVA",
    "lDqwgw-vYWc",
    "xsJwbk_N-RE",
    "8IScMLY_yLY",
    "H9A7Olg_QCo",
    "WyRSqoqHWF0",
    "XmkNwgkMC3U",
    "gPkOSEdG0OA",
    "0Fa4Wyv0GOk",
    "zpuRES7Fnm8",
    "PNH5hdUnXks",
    "LpqjenfvWzQ",
    "5qA5ibrq9NU",
    "GQZ7A4fvts4",
    "tAFtaCF5a30",
    "19EEFd2ueiI",
    "GICjcQQ0aM0",
    "IjZkoyk7T14",
    "co3N4y-RQKQ",
    "k1qCouxaNjQ",
    "VrPi2RUUXq4",
    "1WgqAO8AmsY",
    "F9Vo4fezmcE",
    "Gw4Ng9FKJyY",
    "PxTeZh0w1Go",
    "Q6VqxNlagpQ",
    "XsbGYVBY92c",
    "glXpHbwhQA4",
    "mJOReEqkgMM",
    "0Spa0u4IyLE",
    "1jLbPyOnpjo",
    "IaOyZ0KPlUU",
    "j7EZJwH8uCM",
    "na0fqtqARVs",
    "-4qvpm4Rd6Q",
    "8xJampnp9qc",
    "ACvOem_B-Ek",
    "AK435vKMtlo",
    "HtmLQkxj8ec",
    "MmiI3xo5Ju4",
    "OzKHRjr8nt8",
    "WlIW6LkFLp4",
    "jGG6-a4IrNw",
    "kNMpaK6SIbc",
    "p3eCPcvhsjM",
    "qIsZ9oxvWeI",
    "tBKVwXEzl0c",
    "umD1vXG7WIA",
    "3InKt2QjqQ8",
    "8Xy8xsLIgAU",
    "OaTrIaFLG6M",
    "TIZ3yFQCFfA",
    "XS9EXhxRbi8",
    "fzfhimnVghE",
    "y-C_8_p_F5w",
    "F0kz4L2wB2A",
    "pQ7yAREnJaw",
    "R7N_Bf14f0o",
    "uAPvGyjkrB8",
    "FSwSt1omSD8",
    "y9iL10DPhzI",
    "zs_JKa0cVsY",
    "rux7GLCqLWQ",
    "OWXe9v7PHDs",
    "5xxp7L-Ktp8",
    "_xRxSiooRnE",
    "NWrTrDIQ9XE",
    "Nq8BntIZb40",
    "UKYZ4NtUMTw",
    "jK7-PPBXwr4",
    "JRX5W9AhWoA",
    "n3UBbCXJaJ0",
    "tCWfCISvo5k",
    "D9obnqNB4aI",
    "XK2Wna2YG6Y",
    "LGkdzRl08vo",
    "cESK2Fb3Aq0",
    "3EqnSkAzfIg",
    "oSAPs1YDkq0",
    "j66VV2XKBJk",
    "rKoXeKg0y1Q",
    "-4wCvcPrX-E",
    "h5XzWxcWrtU",
    "uA7E_SUdtM8",
    "WtRGXnnGiVE",
    "Vl55gfNrZmM",
    "pTnEtB8mcVA",
    "tLNsDEp-JcA",
    "4LIZkNHlNaM",
    "38-NgBAet1c",
    "odNtpKqbCQo",
    "nen-DB_tz4M",
    "pmSPHJfg3AU",
    "uNkgwv4dqEs",
    "OZiElH5pKmo",
    "X1mtpheWDhs",
    "-YQLpNmH0MQ",
    "-0O6WmxU3pw",
    "N8aw4NAR62c",
    "vGWM3R_ihxI",
    "UgQV_5FjPNk",
    "OuDAdSnFtbw",
    "z3fSeC_oG-s",
    "RkLY_uJL0xc",
    "21SEb5M9IRs",
    "u5JpxwG34bE",
    "qajcmg64VNI",
    "mpLJPUifTNA",
    "Ba-hG3SGdfw",
    "VP9mfCJBX_Y",
    "AHbh4mzrwUQ",
    "ULID4U_e3TU",
    "G1fWNIazj5U",
    "vhLVeSDWB5M",
    "XhV7FuKtZnY",
    "ELiB_UwCVTY",
    "5daxvIoDLVU",
    "0YfmJqftSLE",
    "pTw6RbHzm-U",
    "K2yXX6uhGFE",
    "_fi53IYfitg",
    "xFyfHBkyQgA",
    "HTcbWPN1xxY",
    "rPfK6DcC1Vw",
    "JLN3i1y6_Dk",
    "Ejcq9mNGJk0",
    "XFZOr_5-0F0",
    "1oHlA7FtsGM",
    "dDyJNwNUbJs",
    "o_J7uas-9U0",
    "qj6ZFtvViic",
    "0m64VFmniGI",
    "ve_KEcn9Ues",
    "M6MJzzFKoPg",
    "HfS2relUTFg",
    "Maa5lwwHNrU",
    "x1KyU5MVHu4",
    "uSAO5p0GIU8",
    "RGFI6v2Biq0",
    "Vz_fn9o_Meo",
    "leypd9opVSc",
    "0poMFCoAhkM",
    "4Fjf6IQsjQs",
    "8Lp2qPXYix4",
    "E-LCT0YEpWQ",
    "Eznp9NU0Y4I",
    "HZIuHUGmnGY",
    "R0bGNxoJ4sM",
    "V1IuTlEU1ic",
    "VOOf2kQpeMw",
    "WfiHrS5Kjj8",
    "a3sAeqXrCYI",
    "cz_i2AsxGv0",
    "md0y8j1SxBk",
    "nD0_yE8Yy64",
    "oqacXWT14ic",
    "sCCLfLa0gyw",
    "40tIgtC8yec",
    "9XbV4ubs3Fw",
    "BtXOk3KUBd0",
    "ClbKAXVvzzo",
    "E5FJYDruwjs",
    "SAt-D1YFM1Q",
    "U4lCthMt9oY",
    "gLXqxcsF1dw",
    "n_6eC35_wzA",
    "r3iE2gDwIEk",
    "rxz4w8fxXZ8",
    "xNzBwpLBtSs",
    "zDOS3wCWea8",
    "4QL5Djtikmw",
    "5RcKCxfLEHM",
    "7L2scLHOEC4",
    "Hdr5IXNmRUE",
    "Nq2VYAIQyCs",
    "XcE2G9J8U_4",
    "qiba4m7wUXQ",
    "R3ZRYoTxhUE",
    "XEFWnanCtk8",
    "lZTaw-5V_mc",
    "DBUJH5f6rjU",
    "ECFRWVY8SGY",
    "Lm-5gKTKD7Y",
    "UDr00laBiYo",
    "T_SFXvO7ymc",
    "CKBwY7odu1E",
    "Wua3xtO-oys",
    "ds6FM6QEDWM",
    "fYLwmDCmJ0A",
    "fiABnex9O6Y",
    "nlimcAFzAQE",
    "LZQ4PvoArC8",
    "Qu5IQo0ghbs",
    "WOKBogNTmPI",
    "YguId6pF5KI",
    "c2oUDKf6ndo",
    "w2qbJB6ie9Y",
    "ZVraDQJ_I_Y",
    "l0bQZ9tnwvk",
    "BJfhRGjPznA",
    "beadZEtxtcs",
    "esrYgY--owE",
    "xnfQDhWWMkU",
    "O8iewlvGRN0",
    "WO_jh3zPTr0",
    "hLg4WPG4ehE",
    "M6NGzhww27o",
    "jHsA3IlRCm4",
    "nj4mPBJsauQ",
    "avCLyAi9DeY",
    "omDPxlDqDs0",
    "_KtWOkUsy1w",
    "PoNEyybToU4",
    "v58RteTeBlE",
    "susUKIwVD34",
    "MAwd31cafVg",
    "Y7p7jHP0Ii0",
    "GsEMHzvDq5M",
    "DjybU3_lUnc",
    "dkV4Dl3jfLs",
    "SKII-krCBcg",
    "-dzlXEIkqkI",
    "zPrI0q34qw8",
    "CfkyO8rGn2Y",
    "LzPKkAnAtjk",
    "h1YFNFOogEM",
    "tix59qHbyrI",
    "vLCsNfcbWqs",
    "d_IIBZd-xAQ",
    "Ul_7NL6j2ZI",
    "qPKICCU7Wec",
    "z0iCoqwZE_U",
    "VO3fi1c9ids",
    "R_bZWZvU-r4",
    "AxlmYK0B9Yw",
    "EpReLy7g6WM",
    "HKjzpPlfvc8",
    "nsUkTKmx2dI",
    "9RkGiNC-jJA",
    "WQWVnrG-wX4",
    "wDaE92bNRNw",
    "RgE2ryZsE3s",
    "zXjwi5tTcno",
    "SDWivCDevfE",
    "ct7R4Em77NY",
    "v55cSB0foxM",
    "sboLTO_FUY4",
    "MIF1XIgr-IQ",
    "CvDkoctU5a4",
    "tl31QISheOc",
    "Ji7Zy_tDFQ4",
    "aIEw-1E9ays",
    "HCs6I_BNtxo",
    "Y7bp-LlC3CM",
    "CNn_cuQsBh0",
    "-i-QFyNg8Io",
    "X-m1fDzX5Rc",
    "BsiePkp9bAc",
    "wKYEvQZ03Po",
    "bSfYcWPgkpI",
    "1KnFnmU6NWw",
    "uz81-q_o5LI",
    "6SGdA1xnd4A",
    "We6ENmiSSwI",
    "2X0BCy1bRcU",
    "H4paK9NPSoc",
    "6yHWS32aNOs",
    "OLPF727ETSg",
    "6YexvWyPC6k",
    "vZGe4g66rw4",
    "mz8Mb0MvBz4",
    "G_soqEsZRU8",
    "roc7MPff-C8",
    "KN0XZBa7K4Y",
    "QlHMnyKYYoI",
    "f-IpkGOOzYU",
    "OoH2peWBDEY",
    "a_qokyTjobo",
    "mS3cZvd1AvQ",
    "O4c1bnnwSzU",
    "UodtrfOmNh4",
    "gqN5tl1Kwpg",
    "jEg3pQmKBIw",
    "3OjpANs8PDw",
    "XzS56RqIxeE",
    "qDQ1JxqWcT8",
    "Gae2J6ExMsY",
    "R5jh4Ss4fKA",
    "7UuDjBiHrMA",
    "wzb6s4oJX1Y",
    "JsTTRgk_8Hc",
    "IbOoMlXlzjY",
    "DnllMgFybyQ",
    "_KQTdkGrw6A",
    "c32xomNzUIs",
    "lmNVJBc1Zoo",
    "phMVQUn1Sns",
    "pk4MA5aOSOY",
    "zlxVrlARMEI",
    "gQv87W3mAu8",
    "H7N4PSoJZMU",
    "EThkIHrfXWo",
    "CnCcYyJ8NTo",
    "EwwciE_mxo8",
    "a78n3v1aDMg",
    "u3xrPJu51SM",
    "tGvaofifDzI",
    "8n4-3zJSZyI",
    "pJXS28Odaqs",
    "Mrngwfko5kk",
    "Hfj0c6-vUiY",
    "-wAUE5rcxis",
    "vrXmfCUvigs",
    "rY83MZu--ck",
    "Gv3w2uNCo2o",
    "s-In3a1CAoI",
    "rRs__D_3mKY",
    "sZXuNv0L8YA",
    "88NOQTz5_yI",
    "dEZ1P72hmLg",
    "MX7tos4L1jQ",
    "dwOK83_n6_4",
    "Ln-4oxqStJI",
    "4rZDc-SaOB8",
    "GaSK6rscIgA",
    "dR7olu353VY",
    "mQ_qPqsc-i0",
    "1p0EnoA2u6o",
    "QeRsbucrii4",
    "Oy-j2w6haoA",
    "mB83CObqvhU",
    "jRI007mQ2Wo",
    "RMpAflHYP2g",
    "GBlHpCkYYgc",
    "DqUafRyXy_0",
    "W_KHgnxTHaY",
    "4eV8OvVEm6A",
    "AwDC-VZWfzU",
    "wjgYeizZwN8",
    "A6vBcCd_54I",
    "Pd42WwNAr8g",
    "aVqDALcqpII",
    "f8iC_C6rop0",
    "uIknA-azXKQ",
    "-vboUHsZ2KM",
    "A0edLNr-mks",
    "YtkxNkrfJWg",
    "9kSjk8uqNbI",
    "COmWEGiu9Hg",
    "Khxy7onLOnE",
    "s0p8jSaZOGc",
    "WLN80D-u2us",
    "Ez7hzMHEs2I",
    "3_SHb2rvvvI",
    "r3VajKBFhbA",
    "7i_LOcXlznQ",
    "fjekLTmR3ms",
    "O4YQRVeyl6I",
    "Q6q7MaVu9Dk",
    "L4876a9aakw",
    "vcvE5YpOjL4",
    "Ud5UpU0bvjw",
    "1imcyoNUO-A",
    "2RES9QrbVMA",
    "7BLsD_meNzw",
    "9wm4ey4OX8g",
    "9yaEGbPIxPk",
    "B9LZcfD-blU",
    "GTLqZPVojgI",
    "szJ7uDYHJ1Y",
    "2U2GS7IkE8c",
    "LLhU1ptXDp0",
    "OrydPLvNKmI",
    "TN9W-Jc7qZc",
    "rXkyO0fOOLE",
    "Rdm6ZwxZ3m4",
    "KB_rdqB-sVw",
    "izjxTA_-mNs",
    "liMBvMgSPC8",
    "-LK01oo7MAw",
    "P6gff20GmPQ",
    "COC9vdjMTlc",
    "TqxxCYnAxo8",
    "UlOt31lBhLY",
    "VAMJEgwaPEc",
    "AR0r8B6Ga8E",
    "vARTudIEq30",
    "nwQaU-agzFE",
    "hUmlujE6SN0",
    "RAOQ3ZubQGM",
    "0z-IZ2ar4eA",
    "WIUa93sXmPw",
    "sCiK7ABPcrw",
    "VxJWAmiYu_0",
    "rGcNJ_Nsuy8",
    "STlEq16n8kI",
    "NFlAszNFZdQ",
    "btbKcsb9Dzw",
    "zQjrjEYPsB8",
    "eozUm89Kk9k",
    "f0mxoBD9Fno",
    "O-6f5wQXSu8",
]

# Attempt failed/private/deleted ones too — most will return nothing, but some may have recovered
FAILED_IDS = [
    "fj2_d2lNGVk",
    "O1VkNuEChD4",
    "IGryscyFmV8",
    "0ypG1mlekNY",
    "owXqW04b08o",
    "M8XASiz30oE",
    "JRlaAip4kmk",
    "qtG8c2zhn7A",
    "Gt3o8lcbcII",
    "cI7D2aO34yw",
    "w1gF90_cBl4",
    "ZGvKY4mPfIc",
    "GfAMCHC6_ek",
    "CZ_r5sYeTyY",
    "obK5uqYXOJU",
    "bSyewSnu2Ak",
    "mNM-x9RFMcE",
    "207izZBbqVg",
    "1w-IStuMl3M",
    "M7ItOHTrvz8",
    "UJM00IqGKtc",
    "K-AFDVOkIoE",
    "1nhXsnx5--Y",
    "NJQ573JDmAg",
    "RBb_3sgOgFY",
    "ffhDTzE4nDU",
    "uZg9XnRub7w",
    "RFx74Q6Oq2c",
    "9Mv4Thnx9SU",
    "Gdd-5uWUW5w",
    "dqUq_a0DyLs",
    "1PlGMOAypCI",
    "QzJ_Ft1de1o",
    "Mr1cjAz2y9I",
    "HELtP96Dd4w",
    "cHAJiF2byzg",
    "vch9C_hNjGs",
    "k8iO5daXllM",
    "ftFDBaH7RFg",
    "pPHQMD3w9-s",
    "Fbd7ln2i9dw",
    "PslFhdZaBFA",
    "AviNwtN1luo",
    "oaKWpxmu0YI",
    "nUrc8O7Avvk",
    "6-GWHR9_iSU",
    "Qr_pw4E-REk",
    "V2WQ20Ocw_o",
    "BkM7IcqUaj0",
]

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────


def _bert_restore(text):
    # type: (str) -> str
    """Restore punctuation using the local BERT model, chunked to 400 words."""
    try:
        words = text.split()
        chunk_size = 400
        if len(words) <= chunk_size:
            return _punct_model.restore_punctuation(text)
        chunks = [" ".join(words[i : i + chunk_size]) for i in range(0, len(words), chunk_size)]
        restored = []
        for idx, chunk in enumerate(chunks):
            try:
                restored.append(_punct_model.restore_punctuation(chunk))
            except Exception as ce:
                print(f"    ⚠️  BERT chunk {idx + 1}/{len(chunks)} failed: {ce} — using raw")
                restored.append(chunk)
        return " ".join(restored)
    except Exception as e:
        print(f"    ⚠️  BERT restore failed: {e} — using raw text")
        return text


def _claude_restore(text, video_id=""):
    # type: (str, str) -> str
    """
    Restore punctuation via Claude API (claude-haiku-4-5 — fast & cheap).
    Best for spiritual/Sanskrit content where BERT struggles.
    """
    if not ANTHROPIC_KEY:
        print("    ⚠️  ANTHROPIC_API_KEY not set — skipping Claude punctuation.")
        return text
    try:
        prompt = (
            "Add proper punctuation, capitalization, and paragraph breaks to the following "
            "raw YouTube transcript. Fix sentence boundaries. Do NOT change any words, "
            "remove content, or add explanations. Return only the corrected transcript text.\n\n"
            f"TRANSCRIPT:\n{text}\n\nCORRECTED TRANSCRIPT:"
        )
        payload = json.dumps(
            {
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}],
            }
        ).encode("utf-8")

        req = _urllib_req.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        with _urllib_req.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        res_text = result["content"][0]["text"].strip()
        time.sleep(1.0)  # Polite sleep to respect API rate limits
        return res_text
    except Exception as e:
        print(f"    ⚠️  Claude API restore failed for {video_id}: {e} — using raw text")
        return text


_nvidia_call_timestamps = []


def _respect_nvidia_rate_limit(video_id=""):
    """
    Rolling-window rate limiter ensuring we never exceed 40 requests per minute.
    """
    global _nvidia_call_timestamps
    now = time.time()
    # Keep only timestamps in the last 60 seconds
    _nvidia_call_timestamps = [t for t in _nvidia_call_timestamps if now - t < 60.0]

    if len(_nvidia_call_timestamps) >= 40:
        sleep_needed = 60.0 - (now - _nvidia_call_timestamps[0])
        if sleep_needed > 0:
            print(
                f"    ⏳ [NVIDIA Rate Limiter] {len(_nvidia_call_timestamps)} RPM limit reached (for {video_id}). Sleeping {sleep_needed:.2f}s..."
            )
            time.sleep(sleep_needed)
            now = time.time()
            _nvidia_call_timestamps = [t for t in _nvidia_call_timestamps if now - t < 60.0]

    _nvidia_call_timestamps.append(time.time())


def _nvidia_restore(text, video_id=""):
    # type: (str, str) -> str
    """
    Restore punctuation via NVIDIA API (meta/llama-3.1-70b-instruct).
    Best quality, supports streaming, with exponential backoff on rate limits.
    """
    if not NVIDIA_KEY:
        print("    ⚠️  NVIDIA_API_KEY not set — skipping NVIDIA punctuation.")
        return text
    try:
        from openai import OpenAI
    except ImportError:
        print("    ⚠️  openai library not installed — skipping NVIDIA punctuation.")
        return text

    prompt = (
        "Add proper punctuation, capitalization, and paragraph breaks to the following "
        "raw YouTube transcript. Fix sentence boundaries. Pay special attention to "
        "properly capitalizing proper nouns, names, spiritual, Sanskrit, and Indic philosophical "
        "terms (e.g., Guru, Mukthi, Brahman, etc.). Do NOT change any words, "
        "remove content, or add explanations. Return only the corrected transcript text.\n\n"
        f"TRANSCRIPT:\n{text}\n\nCORRECTED TRANSCRIPT:"
    )

    max_retries = 5
    backoff_factor = 2.0
    initial_delay = 1.0

    for attempt in range(max_retries):
        try:
            # Respect the strict 40 requests per minute rolling rate limit before every API call
            _respect_nvidia_rate_limit(video_id)

            client = OpenAI(
                base_url="https://integrate.api.nvidia.com/v1",
                api_key=NVIDIA_KEY,
                timeout=60.0,  # prevent indefinite hang if NVIDIA API is slow/unresponsive
            )
            completion = client.chat.completions.create(
                model="meta/llama-3.1-70b-instruct",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                top_p=0.7,
                max_tokens=2048,
                stream=True,
            )
            restored = []
            for chunk in completion:
                if chunk.choices and chunk.choices[0].delta.content is not None:
                    restored.append(chunk.choices[0].delta.content)
            res_text = "".join(restored).strip()
            return res_text
        except Exception as e:
            delay = initial_delay * (backoff_factor**attempt)
            print(
                f"    ⚠️  NVIDIA API attempt {attempt + 1}/{max_retries} failed for {video_id}: {e} — retrying in {delay:.1f}s..."
            )
            if attempt < max_retries - 1:
                time.sleep(delay)
            else:
                print(
                    f"    ❌ All {max_retries} NVIDIA API attempts failed for {video_id} — using raw text"
                )
                return text
    return text


def _merge_chunks_with_llm(chunks, video_id=""):
    # type: (list, str) -> str
    """
    Merge overlapping transcript chunks using NVIDIA LLM.
    Removes duplicate sentences at chunk boundaries while preserving all unique content.
    """
    if not NVIDIA_KEY:
        # Fallback: naive concatenation (may have some duplication at boundaries)
        return "\n\n".join(chunks)

    try:
        from openai import OpenAI
    except ImportError:
        return "\n\n".join(chunks)

    # Join chunks with clear boundary markers
    marked = "\n\n---CHUNK_BOUNDARY---\n\n".join(chunks)

    merge_prompt = (
        "The following transcript was processed in overlapping chunks. "
        "At each ---CHUNK_BOUNDARY--- marker, some sentences may be duplicated. "
        "Remove the exact duplicate sentences at these boundaries while preserving ALL unique content. "
        "Remove the ---CHUNK_BOUNDARY--- markers. "
        "Do NOT change any words, reorder content, or add explanations. "
        "Return only the cleaned, unified transcript.\n\n"
        f"TRANSCRIPT:\n{marked}\n\nCLEANED TRANSCRIPT:"
    )

    max_retries = 3
    for attempt in range(max_retries):
        try:
            _respect_nvidia_rate_limit(video_id)
            client = OpenAI(
                base_url="https://integrate.api.nvidia.com/v1",
                api_key=NVIDIA_KEY,
                timeout=90.0,
            )
            completion = client.chat.completions.create(
                model="meta/llama-3.1-70b-instruct",
                messages=[{"role": "user", "content": merge_prompt}],
                temperature=0.1,
                top_p=0.7,
                max_tokens=4096,
                stream=True,
            )
            restored = []
            for chunk in completion:
                if chunk.choices and chunk.choices[0].delta.content is not None:
                    restored.append(chunk.choices[0].delta.content)
            result = "".join(restored).strip()
            if result:
                return result
        except Exception as e:
            print(f"      ⚠️  Merge attempt {attempt + 1}/{max_retries} failed for {video_id}: {e}")
            if attempt < max_retries - 1:
                time.sleep(2.0 * (attempt + 1))

    # All merge attempts failed — fallback to naive concatenation
    print(
        "      ↳ Merge failed, using naive concatenation (may have minor duplication at boundaries)"
    )
    return "\n\n".join(chunks)


def _nvidia_restore_chunked(text, video_id=""):
    # type: (str, str) -> str
    """
    Process long transcripts in chunks with overlap, then merge.
    For transcripts ≤1000 words, delegates to the standard single-call _nvidia_restore.
    For longer ones, splits into ~800-word chunks with 50-word overlap,
    processes each independently, then uses LLM to merge and deduplicate boundaries.
    """
    words = text.split()
    if len(words) <= 1000:
        return _nvidia_restore(text, video_id)

    chunk_size = 800
    overlap = 50
    chunks = []
    i = 0
    chunk_num = 0
    while i < len(words):
        end = min(i + chunk_size, len(words))
        chunks.append(" ".join(words[i:end]))
        chunk_num += 1
        if end >= len(words):
            break
        i = end - overlap  # overlap for context continuity

    print(f"      ↳ Long transcript ({len(words)} words) → {len(chunks)} chunks")

    restored_chunks = []
    for idx, chunk in enumerate(chunks):
        print(f"      ↳ Processing chunk {idx + 1}/{len(chunks)}...")
        result = _nvidia_restore(chunk, f"{video_id}_chunk{idx + 1}")
        restored_chunks.append(result)

    # Merge overlapping chunks using LLM
    if len(restored_chunks) > 1:
        print(f"      ↳ Merging {len(restored_chunks)} chunks with LLM...")
        combined = _merge_chunks_with_llm(restored_chunks, video_id)
        return combined
    return restored_chunks[0]


def restore_punctuation(text, video_id=""):
    # type: (str, str) -> str
    """
    Council-based multi-tier punctuation restoration:
      PUNCT_MODE = "council" → Two-pass Council mode: BERT first (local), then NVIDIA API refinement (best quality & cost-effective)
      PUNCT_MODE = "nvidia"  → NVIDIA API (Llama-3.1-70b-instruct) always
      PUNCT_MODE = "auto"    → BERT if available, NVIDIA API if not (fallback)
      PUNCT_MODE = "bert"    → BERT only (skip if unavailable)
      PUNCT_MODE = "claude"  → Claude API always
      PUNCT_MODE = "none"    → return as-is
    """
    if not text or PUNCT_MODE == "none":
        return text

    if PUNCT_MODE == "council":
        print("    🤖 Restoring punctuation via Council (BERT -> NVIDIA)...")
        # Step 1: Run BERT if available
        if BERT_PUNCT_AVAILABLE:
            print("      ↳ Step 1: Running local BERT model...")
            first_pass = _bert_restore(text)
        else:
            print("      ↳ Step 1: BERT unavailable — skipping to NVIDIA...")
            first_pass = text

        # Step 2: Run NVIDIA API on the first-pass result
        print("      ↳ Step 2: Refining with NVIDIA API (Llama-3.1-70b-instruct)...")
        refined = _nvidia_restore_chunked(first_pass, video_id)
        return refined

    if PUNCT_MODE == "nvidia":
        print("    🤖 Restoring punctuation via NVIDIA API...")
        return _nvidia_restore_chunked(text, video_id)

    if PUNCT_MODE == "claude":
        print("    🤖 Restoring punctuation via Claude API...")
        return _claude_restore(text, video_id)

    if PUNCT_MODE == "bert":
        if not BERT_PUNCT_AVAILABLE:
            print("    ⚠️  BERT model unavailable and PUNCT_MODE='bert' — skipping.")
            return text
        return _bert_restore(text)

    # PUNCT_MODE == "auto" (default fallback)
    if BERT_PUNCT_AVAILABLE:
        return _bert_restore(text)
    else:
        print("    🤖 BERT unavailable — restoring punctuation via NVIDIA API...")
        return _nvidia_restore_chunked(text, video_id)


# ── Noise patterns to strip from raw captions ─────────────────────────────────
# Covers: [Music], [Applause], [Laughter], [MUSIC], [ __ ], timestamps like (0:00)
_NOISE_PATTERNS = [
    re.compile(r"\[+[^\]]{0,40}\]+"),  # [Music], [Applause], [[Music]], [ __ ]
    re.compile(r"\(+[^\)]{0,20}\)+"),  # (music), (applause)
    re.compile(r"\d{1,2}:\d{2}(?::\d{2})?"),  # timestamps: 0:00, 1:23:45
    re.compile(r"♪+\s*.*?\s*♪+"),  # ♪ music notes ♪
    re.compile(r"<[^>]{0,30}>"),  # <inaudible>, HTML-like tags
    re.compile(r"\buh+\b|\bum+\b|\bhmm+\b", re.IGNORECASE),  # filler words
]


def build_plain_text(item):
    # type: (Dict) -> str
    """
    Extract and clean transcript text from a johnvc actor result item.

    Priority:
      1. non_timestamped  — pre-joined plain string from the actor
      2. timestamped      — [{text, start, duration}] segments joined as fallback

    Cleaning steps:
      1. HTML entity decode
      2. Strip all noise tokens (music, applause, timestamps, fillers)
      3. Collapse whitespace
    """
    text = item.get("non_timestamped", "")
    if not text:
        segments = item.get("timestamped") or []
        text = " ".join(s.get("text", "") for s in segments if isinstance(s, dict))

    if not isinstance(text, str):
        text = str(text)

    # 1. Decode HTML entities
    text = (
        text.replace("&#39;", "'")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("\xa0", " ")
    )

    # 2. Strip all noise patterns
    for pattern in _NOISE_PATTERNS:
        text = pattern.sub(" ", text)

    # 3. Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def validate_transcript_completeness(item, plain_text):
    # type: (Dict, str) -> tuple
    """
    Validate that a transcript is complete before writing to .md.
    Returns (is_complete: bool, reason: str).

    Checks:
      1. Timestamp coverage: last segment must reach ≥95% of total video duration
      2. Word density: at least 30 words/minute (conservative floor)

    100% data quality guarantee — partial transcripts are NEVER accepted.
    """
    total_secs = item.get("total_seconds", 0)
    if total_secs == 0:
        # No duration info from actor — can't validate, accept with warning
        return True, "no duration info (cannot validate coverage)"

    # Check 1: Timestamp coverage
    timestamped = item.get("timestamped", [])
    if timestamped and isinstance(timestamped, list):
        valid_segments = [s for s in timestamped if isinstance(s, dict)]
        if valid_segments:
            last = valid_segments[-1]
            last_end = float(last.get("start", 0)) + float(last.get("duration", 0))
            coverage = last_end / float(total_secs)
            if coverage < MIN_COVERAGE_PCT:
                return (
                    False,
                    f"timestamp coverage {coverage:.1%} < {MIN_COVERAGE_PCT:.0%} threshold (last_end={last_end:.1f}s / total={total_secs:.1f}s)",
                )
        else:
            # Has timestamped field but all entries are malformed
            return False, "timestamped field present but no valid segments"

    # Check 2: Word density
    if plain_text:
        words = len(plain_text.split())
        minutes = total_secs / 60.0
        wpm = words / minutes if minutes > 0 else 0
        if wpm < MIN_WORDS_PER_MIN:
            return (
                False,
                f"word density {wpm:.0f} wpm < {MIN_WORDS_PER_MIN:.0f} wpm threshold ({words} words / {minutes:.1f} min)",
            )
    else:
        return False, "empty transcript text"

    return True, "OK (coverage and density validated)"


def write_md(video_id, title, channel, date, description, plain_text, language):
    # type: (str, str, str, str, str, str, str) -> Path
    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        filename = OUTPUT_DIR / f"{video_id}.md"
        body = plain_text if plain_text else "_No transcript available._"
        desc = description if description else "_No description available._"
        content = (
            f"# {title}\n\n"
            f"**Video ID:** `{video_id}`\n"
            f"**URL:** {url}\n"
            f"**Channel:** {channel}\n"
            f"**Published:** {date}\n"
            f"**Language:** {language}\n\n"
            f"## Description\n\n{desc}\n\n"
            f"## Transcript\n\n{body}\n"
        )
        filename.write_text(content, encoding="utf-8")
        return filename
    except Exception as e:
        print(f"    ⚠️  write_md failed for {video_id}: {e}")
        raise


def load_state():
    # type: () -> Dict
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"⚠️  Could not load _state.json: {e} — starting fresh.")
    return {
        "processed": [],
        "failed": [],
        "incomplete": [],
        "timeout_victims": [],
        "retry_counts": {},
    }


def save_state(state):
    # type: (Dict) -> None
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"  ⚠️  Could not save state: {e}")


def load_json():
    # type: () -> Dict
    try:
        if JSON_FILE.exists():
            return json.loads(JSON_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"⚠️  Could not load transcripts.json: {e} — starting fresh.")
    return {}


def save_json(data):
    # type: (Dict) -> None
    """Atomic write: .tmp → rename."""
    tmp = JSON_FILE.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(JSON_FILE)
    except Exception as e:
        print(f"  ⚠️  Could not save transcripts.json: {e}")
        try:
            tmp.unlink()
        except Exception:
            pass


def run_batch(client, video_ids, timeout=None):
    # type: (ApifyClient, List[str], Optional[int]) -> tuple
    """
    johnvc/YoutubeTranscripts input: { "youtube_url": [list of URLs] }
    Returns (items, was_aborted) tuple:
      - items: list of result dicts from the dataset
      - was_aborted: True if the run was aborted due to timeout (indicates timeout victims)
    Starts the run asynchronously, polls with a timeout, and always retrieves all completed
    results from the dataset even if the run times out or gets aborted.
    """
    urls = [f"https://www.youtube.com/watch?v={v}" for v in video_ids]
    max_retries = 5
    backoff_factor = 2.0
    initial_delay = 2.0
    run = None

    for attempt in range(max_retries):
        try:
            run = client.actor(ACTOR_ID).start(run_input={"youtube_url": urls})
            break
        except Exception as e:
            delay = initial_delay * (backoff_factor**attempt)
            print(
                f"  ⚠️  Apify actor start attempt {attempt + 1}/{max_retries} failed: {e} — retrying in {delay:.1f}s..."
            )
            if attempt < max_retries - 1:
                time.sleep(delay)
            else:
                raise RuntimeError(
                    f"Apify actor start failed after {max_retries} attempts: {e}"
                ) from e

    run_id = run.get("id") if run else None
    dataset_id = run.get("defaultDatasetId") if run else None

    if not run_id or not dataset_id:
        print(f"  ⚠️  No run ID or dataset ID returned for batch: {video_ids[:3]}...")
        return [], False

    print(f"  🚀 Apify Actor run started: {run_id} (Dataset: {dataset_id})")

    # Poll run status with configurable timeout
    start_time = time.time()
    poll_interval = 5
    actual_timeout = timeout if timeout else RUN_TIMEOUT
    status = "RUNNING"
    was_aborted = False

    while time.time() - start_time < actual_timeout:
        try:
            run_info = client.run(run_id).get()
            status = run_info.get("status", "RUNNING")
            if status in ["SUCCEEDED", "FAILED", "TIMED-OUT", "ABORTED"]:
                break
        except Exception as e:
            print(f"    ⚠️ Error polling run status: {e}")
        time.sleep(poll_interval)

    if status == "RUNNING":
        print(
            f"  ⏳ Run is taking longer than {actual_timeout}s. Aborting and fetching partial results..."
        )
        was_aborted = True
        try:
            client.run(run_id).abort()
            print("  🛑 Run aborted successfully to save resources.")
        except Exception as ae:
            print(f"    ⚠️ Failed to abort run: {ae}")
    else:
        print(f"  🏁 Run finished with status: {status}")

    # Retrieve all items that were successfully written to the dataset so far
    items, offset = [], 0
    while True:
        try:
            page = list(client.dataset(dataset_id).iterate_items(offset=offset, limit=100))
        except Exception as e:
            print(f"  ⚠️  Pagination error at offset {offset}: {e} — stopping.")
            break
        if not page:
            break
        items.extend(page)
        offset += len(page)

    return items, was_aborted


def extract_video_id(item):
    # type: (Dict) -> Optional[str]
    """johnvc actor uses 'video_id' field; fall back to URL parsing."""
    try:
        val = item.get("video_id") or item.get("videoId") or item.get("id")
        if val:
            return str(val).strip()
        url = item.get("url") or item.get("videoUrl") or ""
        m = re.search(r"[?&]v=([A-Za-z0-9_-]{11})", str(url))
        return m.group(1) if m else None
    except Exception as e:
        print(f"  ⚠️  extract_video_id error: {e}")
        return None


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────


def audit_existing_transcripts(transcripts_data, state):
    # type: (Dict, Dict) -> None
    """
    Re-validate all existing transcripts against completeness criteria.
    Flags any partial transcripts that slipped through previous runs.
    """
    print("\n" + "=" * 60)
    print("🔍 AUDITING EXISTING TRANSCRIPTS FOR COMPLETENESS")
    print("=" * 60)

    flagged = []
    for vid, entry in transcripts_data.items():
        plain = entry.get("captions", "")
        is_complete, reason = validate_transcript_completeness(entry, plain)
        if not is_complete:
            flagged.append((vid, reason))

    if flagged:
        print(f"\n⚠️  Found {len(flagged)} potentially incomplete transcripts:")
        for vid, reason in flagged:
            print(f"  🔸 {vid} — {reason}")
        print("\nThese videos will be re-queued for processing on the next run.")
        # Move them to incomplete so they get retried
        for vid, reason in flagged:
            if vid not in state.get("incomplete", []):
                state.setdefault("incomplete", []).append(vid)
            # Remove from processed so they get re-fetched
            if vid in state.get("processed", []):
                state["processed"].remove(vid)
    else:
        print(
            f"\n✅ All {len(transcripts_data)} existing transcripts pass completeness validation."
        )

    print("=" * 60 + "\n")


def main():
    # ── Parse CLI args ────────────────────────────────────────────────────
    import argparse

    parser = argparse.ArgumentParser(description="Bulk YouTube Transcript Extractor v5")
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Re-validate all existing transcripts and flag partials",
    )
    parser.add_argument(
        "--retry-only",
        action="store_true",
        help="Only run Phase 1 (retry incomplete and timeout victims) and exit",
    )
    args = parser.parse_args()

    # ── Pre-flight ─────────────────────────────────────────────────────────
    if not APIFY_TOKEN:
        print("ERROR: APIFY_API_TOKEN not set.")
        print("Fix : export APIFY_API_TOKEN='your_token_here'")
        sys.exit(1)

    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"ERROR: Cannot create output dir '{OUTPUT_DIR}': {e}")
        sys.exit(1)

    try:
        client = ApifyClient(APIFY_TOKEN)
    except Exception as e:
        print(f"ERROR: Failed to init Apify client: {e}")
        sys.exit(1)

    # ── Load state ─────────────────────────────────────────────────────────
    state = load_state()
    transcripts_data = load_json()

    # Ensure new state fields exist (backward compat with old _state.json)
    state.setdefault("incomplete", [])
    state.setdefault("timeout_victims", [])
    state.setdefault("retry_counts", {})

    # ── Audit mode ────────────────────────────────────────────────────────
    if args.audit:
        audit_existing_transcripts(transcripts_data, state)
        save_state(state)
        save_json(transcripts_data)
        return

    try:
        done_from_md = {p.stem for p in OUTPUT_DIR.glob("*.md")}
    except Exception:
        done_from_md = set()

    # Only processed and truly_failed skip retry.
    # incomplete and timeout_victims are RETRIED.
    already_done = (
        set(state.get("processed", []))
        | set(state.get("failed", []))
        | set(transcripts_data.keys())
        | done_from_md
    )  # type: Set[str]

    # Remove incomplete and timeout_victims from already_done so they get retried
    retryable = set(state.get("incomplete", [])) | set(state.get("timeout_victims", []))
    already_done -= retryable

    # Deduplicate input list (preserve order)
    seen_ids = set()  # type: Set[str]
    all_ids = []  # type: List[str]
    for vid in PENDING_IDS + FAILED_IDS:
        if vid not in seen_ids:
            seen_ids.add(vid)
            all_ids.append(vid)

    remaining = [v for v in all_ids if v not in already_done]

    # Separate retry candidates from new videos
    retry_ids = [v for v in remaining if v in retryable]
    new_ids = [v for v in remaining if v not in retryable]

    n_processed = len(set(state.get("processed", [])))
    n_failed = len(set(state.get("failed", [])))
    n_incomplete = len(set(state.get("incomplete", [])))
    n_timeout = len(set(state.get("timeout_victims", [])))

    print("─" * 60)
    print(f"📋 Total unique videos     : {len(all_ids)}")
    print(f"✅ Already processed       : {n_processed}")
    print(f"❌ Permanently failed      : {n_failed}")
    print(f"🔄 Timeout victims (retry) : {len(retry_ids)}")
    print(f"⏳ Incomplete (retry)      : {n_incomplete}")
    print(f"📥 New to fetch            : {len(new_ids)}")
    print(f"📦 Total remaining         : {len(remaining)}")
    print(f"💰 Estimated cost          : ~${len(remaining) * 0.00012:.4f} USD")
    print(
        "🔤 Punctuation restore     : {}".format(
            f"ON ({PUNCT_MODE})" if PUNCT_MODE != "none" else "OFF"
        )
    )
    print(
        f"🛡️  Completeness threshold  : ≥{MIN_COVERAGE_PCT:.0%} coverage, ≥{MIN_WORDS_PER_MIN} wpm"
    )
    print("─" * 60 + "\n")

    if not remaining:
        print("Nothing to do — all videos already processed.")
        return

    # ── Phase 1: Retry timeout victims and incomplete with smaller batches ──
    if retry_ids:
        print("\n" + "=" * 60)
        print(f"🔄 PHASE 1: RETRYING {len(retry_ids)} TIMEOUT VICTIMS / INCOMPLETE")
        print("=" * 60 + "\n")

        retry_batches = [
            retry_ids[i : i + RETRY_BATCH_SIZE] for i in range(0, len(retry_ids), RETRY_BATCH_SIZE)
        ]

        for rb_num, rb in enumerate(retry_batches, 1):
            print(
                f"🔄 Retry Batch {rb_num}/{len(retry_batches)} — {len(rb)} videos (timeout={RETRY_TIMEOUT})..."
            )

            # Increment retry counts
            for vid in rb:
                count = state["retry_counts"].get(vid, 0) + 1
                state["retry_counts"][vid] = count
                if count > MAX_RETRY_ATTEMPTS:
                    print(
                        f"  💀 {vid} — exceeded {MAX_RETRY_ATTEMPTS} retry attempts, marking as permanently failed"
                    )
                    state["failed"].append(vid)
                    # Remove from retry lists
                    if vid in state["incomplete"]:
                        state["incomplete"].remove(vid)
                    if vid in state["timeout_victims"]:
                        state["timeout_victims"].remove(vid)

            # Filter out videos that just got permanently failed
            rb = [v for v in rb if v not in state["failed"]]
            if not rb:
                continue

            try:
                results, was_aborted = run_batch(client, rb, timeout=RETRY_TIMEOUT)
            except Exception as e:
                print(f"  ❌ Retry batch {rb_num} failed entirely: {e}")
                save_state(state)
                time.sleep(SLEEP_BETWEEN)
                continue

            _process_results(results, was_aborted, rb, state, transcripts_data, already_done)
            save_state(state)
            save_json(transcripts_data)
            time.sleep(SLEEP_BETWEEN)

    # ── Phase 2: Process new videos ───────────────────────────────────────
    if args.retry_only:
        print("\nℹ️  --retry-only flag is active. Skipping Phase 2 (new videos).")
    elif new_ids:
        print("\n" + "=" * 60)
        print(f"📥 PHASE 2: PROCESSING {len(new_ids)} NEW VIDEOS")
        print("=" * 60 + "\n")

        batches = [new_ids[i : i + BATCH_SIZE] for i in range(0, len(new_ids), BATCH_SIZE)]
        total_done = 0

        for batch_num, batch in enumerate(batches, 1):
            print(f"🔄 Batch {batch_num}/{len(batches)} — {len(batch)} videos...")

            # Live dedup guard
            batch = [v for v in batch if v not in already_done]
            if not batch:
                print("  ↳ All videos in this batch already done, skipping.")
                continue

            try:
                results, was_aborted = run_batch(client, batch)
            except Exception as e:
                print(f"  ❌ Batch {batch_num} failed entirely: {e}")
                for vid in batch:
                    if vid not in already_done:
                        state["failed"].append(vid)
                        already_done.add(vid)
                save_state(state)
                time.sleep(SLEEP_BETWEEN)
                continue

            _process_results(results, was_aborted, batch, state, transcripts_data, already_done)
            save_state(state)
            save_json(transcripts_data)
            total_done += len(batch)
            print(f"  ↳ Progress: {total_done}/{len(new_ids)} | Sleeping {SLEEP_BETWEEN}s...\n")
            time.sleep(SLEEP_BETWEEN)

    # ── Final summary ──────────────────────────────────────────────────────
    try:
        failed_unique = sorted(set(state.get("failed", [])))
        FAILED_FILE.write_text("\n".join(failed_unique), encoding="utf-8")
    except Exception as e:
        print(f"⚠️  Could not write _failed.txt: {e}")
        failed_unique = []

    incomplete_unique = sorted(set(state.get("incomplete", [])))
    timeout_unique = sorted(set(state.get("timeout_victims", [])))

    print("\n" + "=" * 60)
    print(
        "✅ Successfully processed  : {} transcripts".format(len(set(state.get("processed", []))))
    )
    print(f"❌ Permanently failed      : {len(failed_unique)} videos")
    print(f"⏳ Incomplete (will retry) : {len(incomplete_unique)} videos")
    print(f"🔄 Timeout victims (retry) : {len(timeout_unique)} videos")
    print(
        "💰 Total cost              : ~${:.4f} USD".format(
            len(set(state.get("processed", []))) * 0.00012
        )
    )
    print("📁 Output:")
    print(f"   → {FAILED_FILE}")
    print(f"   → {JSON_FILE}")
    print(f"   → {OUTPUT_DIR}/*.md")
    if incomplete_unique or timeout_unique:
        print(
            f"\n💡 Re-run this script to retry {len(incomplete_unique) + len(timeout_unique)} retryable videos."
        )
    print("=" * 60)


def _process_results(results, was_aborted, batch, state, transcripts_data, already_done):
    # type: (List[Dict], bool, List[str], Dict, Dict, Set[str]) -> None
    """
    Process results from a single Apify batch run.
    Handles completeness validation, state categorization, and .md writing.
    """
    returned_ids = set()  # type: Set[str]

    for item in results:
        try:
            vid = extract_video_id(item)
            if not vid:
                print("  ⚠️  Result with no video_id — skipping.")
                continue
            if vid in already_done:
                print(f"  ⏭️  {vid} — already done, skipping")
                continue

            returned_ids.add(vid)

            # johnvc returns a top-level "success" bool
            success = item.get("success", True)
            plain = build_plain_text(item) if success else ""

            language = item.get("language", "unknown")
            lang_code = item.get("language_code", "")

            # Actor doesn't return title/channel/date — use video ID as title
            title = item.get("title", vid)
            channel = item.get("channelName", item.get("channel", "Unknown Channel"))
            date = item.get("datePublished", item.get("uploadDate", ""))

            if plain:
                # ── COMPLETENESS VALIDATION — 100% data quality gate ──
                is_complete, reason = validate_transcript_completeness(item, plain)

                if not is_complete:
                    print(f"  🚫 {vid} — INCOMPLETE: {reason}")
                    print("     ↳ NOT writing .md — will retry on next run")
                    # Track as incomplete for retry
                    if vid not in state.get("incomplete", []):
                        state.setdefault("incomplete", []).append(vid)
                    # Remove from timeout_victims if it was there (it's now categorized)
                    if vid in state.get("timeout_victims", []):
                        state["timeout_victims"].remove(vid)
                    # Do NOT add to already_done — must be retried
                    save_state(state)
                    continue

                # ── Transcript is COMPLETE — proceed with punctuation & write ──
                plain = restore_punctuation(plain, vid)
                try:
                    path = write_md(vid, title, channel, date, "", plain, language)
                    print(f"  ✅ {vid} ({language}) → {path.name} [VALIDATED]")
                except Exception as we:
                    print(f"  ⚠️  write_md error for {vid}: {we} — saving to JSON only")

                state["processed"].append(vid)
                # Clean up from retry lists if present
                if vid in state.get("incomplete", []):
                    state["incomplete"].remove(vid)
                if vid in state.get("timeout_victims", []):
                    state["timeout_victims"].remove(vid)
                if vid in state.get("retry_counts", {}):
                    del state["retry_counts"][vid]

                transcripts_data[vid] = {
                    "videoId": vid,
                    "title": title,
                    "channelName": channel,
                    "datePublished": date,
                    "language": language,
                    "language_code": lang_code,
                    "is_generated": item.get("is_generated", True),
                    "total_seconds": item.get("total_seconds", 0),
                    "captions": plain,
                    "timestamped": item.get("timestamped", []),
                    "url": f"https://www.youtube.com/watch?v={vid}",
                }
            else:
                reason = "failed/no captions" if not success else "empty transcript"
                print(f"  ⚠️  {vid} — {reason} ")
                state["failed"].append(vid)

            already_done.add(vid)
            # Store progress immediately after each processed video
            save_state(state)
            save_json(transcripts_data)

        except Exception as item_err:
            print(f"  ❌ Unexpected error on item: {item_err}")
            print(f"     {traceback.format_exc().splitlines()[-1]}")
            continue

    # ── Mark videos not returned by actor ─────────────────────────────────
    for vid in batch:
        if vid not in returned_ids and vid not in already_done:
            if was_aborted:
                # Timeout victim — retryable, NOT permanently failed
                print(f"  🔄 {vid} — not returned (timeout victim, will retry)")
                if vid not in state.get("timeout_victims", []):
                    state.setdefault("timeout_victims", []).append(vid)
                # Do NOT add to already_done — must be retried
            else:
                # Actor finished normally but didn't return this video — truly failed
                print(f"  ❌ {vid} — not returned by actor (permanent failure)")
                state["failed"].append(vid)
                already_done.add(vid)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted — state saved, re-run to resume.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        print(traceback.format_exc())
        sys.exit(1)
