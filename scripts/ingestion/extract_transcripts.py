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
import json
import time
import re
import sys
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Set

# ─────────────────────────────────────────────
# DEPENDENCY CHECKS
# ─────────────────────────────────────────────
try:
    from apify_client import ApifyClient
except ImportError:
    print("ERROR: apify-client not installed.  Fix: pip install apify-client")
    sys.exit(1)

try:
    import urllib.request as _urllib_req
    import urllib.error as _urllib_err
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
    print("⚠️  Punctuation model failed to load: {} — will use Claude API fallback.".format(e))

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
APIFY_TOKEN     = os.environ.get("APIFY_API_TOKEN", "")
ANTHROPIC_KEY   = os.environ.get("ANTHROPIC_API_KEY", "")
NVIDIA_KEY      = os.environ.get("NVIDIA_API_KEY", "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")
ACTOR_ID        = "johnvc/YoutubeTranscripts"   # ✅ tested, confirmed working
BATCH_SIZE      = 50                             # videos per Apify run
SLEEP_BETWEEN   = 3                              # seconds between batches
OUTPUT_DIR      = Path("transcripts")
STATE_FILE      = OUTPUT_DIR / "_state.json"
FAILED_FILE     = OUTPUT_DIR / "_failed.txt"
JSON_FILE       = OUTPUT_DIR / "transcripts.json"

# Punctuation mode:
#   "nvidia" → NVIDIA API (Llama-3.1-70b-instruct) always (best quality, custom rate limits)
#   "auto"   → BERT if available, Claude API if not  (default)
#   "bert"   → BERT only (skip if unavailable)
#   "claude" → Claude API always (best quality for Sanskrit/spiritual terms)
#   "none"   → skip punctuation entirely
PUNCT_MODE = "nvidia"

# ─────────────────────────────────────────────
# VIDEO IDs
# ─────────────────────────────────────────────

PENDING_IDS = [
  "UNdwPjyLGn0", "Js7ongWaW64", "oXRZhJTHuOA", "zGOKGrTNlk4", "4_Fqfew1PRk", "idoWVpnJz-Y", "Vr3PS2DdbDU",
  "l6svaRx35TI", "KTlY-lHs_Ew", "pTnZt0SqDFM", "nQpRoOOu5Yc", "d0v8RE6i0GM", "vjEsXpEtpH4", "AyUE-2Uh5Vg",
  "WfkCDNu4SuE", "VTx4G0KEuUE", "1kS_mQaBLdg", "W2ZzApmqJmo", "Tc8f9ZasRRM", "-yGLiryVQoQ", "Ji-hdW1t30g",
  "U1qRvz3hnMA", "LapJqYf9hzI", "Z7w7soyXmHs", "PFNP4c1cOSI", "XFFgRTgP8Rs", "jy4hcpUSBms", "qDSfb0DZ0PE",
  "hqre34QIMZg", "xUO_WoOlWmI", "XMzZe5aEmTo", "RvgN5Mfbd5A", "3WnNyhhB_4w", "F-hNATzOz2I", "6j6EGVpQkI8",
  "aqSM9LwqWgA", "5YJ6vynFWFc", "Ao8Rhhl9E8k", "E8N04l1Lptk", "EhY6npcnSs8", "s6B81c2uTGg", "MJYpyUlwxg0",
  "Xk1KsO3efP4", "oZRQoiRe7s4", "tegTDWT3SDc", "Fn62UQTIMEk", "PnvNqgTyIFI", "LFTx6ZYMZ1g", "CQEGJ0OaIPo",
  "zGhlBQ8iWl4", "8p3zqYg5wuo", "aJIunwxx3NI", "WwgBOejW_pI", "TXAKaPwrBy0", "q15gR1aGjVs", "bMGaQ2nUE5Y",
  "07NOYJmkkFo", "qJxGtSDiayM", "ZD1nQPtpojM", "3ITFXvYIPqg", "oSqD_BvF7vA", "TQ0TGyaByhs", "x1Neqc9ytqE",
  "cxgHFX04RtQ", "77dJnbTCwsA", "D-RK1E9uoP8", "b-MkLkpTeVY", "FP5O9F9JiOk", "-pBQ6Sy444o", "p2HecXyM3tE",
  "uvhEf3ToMHI", "vNj7OSHos1I", "cu-Tx7ehQvM", "yJoWk10CSjg", "2seBB2oByZc", "vIUY446FVPw", "7b6tnI7VmB4",
  "bh_kjn-1CAY", "L09zAtTcwes", "zvRiparLGl8", "69IrsSXeBTg", "igSp4H0OWLE", "iikr2xzAK6Y", "k0GsZxWhjSE",
  "ZaZOJ6gazYM", "mbhdVEKEbLg", "uGosHULQQk0", "QWKFjbNhiNw", "h8DQ0GlvD8I", "X3LKG0Ycl3A", "co9vrSiN8ak",
  "M_BYTcsLQuY", "o_eg6YTifRE", "utRatnFr-S8", "5Tdb7hBwX88", "4ytgjpow498", "0u9oe-5HPmk", "8fKvjHOD_kQ",
  "1sMxPhQcvEA", "b6nQnYzo_bY", "stUPu1-W4bE", "6EHw_0gYD5w", "6rLvPzNyLRw", "OzgA9wYM6Oc", "tDcy09esbe8",
  "qQmrTz6i2x4", "5hNCT4duOgc", "r_l2RNcSPPA", "I6yC-aUQUvw", "Vt_CjAdzebM", "iIduE7RwihM", "aSNQUkuyB18",
  "tl2Ek-QakME", "g1tezETHrfY", "1J0HpmGWsZs", "nCK4-w8xu9Y", "zFOxZ2oo8-U", "3weAVHuSCxg", "U23yKxWbIcI",
  "x-mTRlE0TC4", "CrZuPkgwA6Q", "ajMAwlKh3YM", "nCkbv_lvFfg", "mmpmX3-qfc4", "BZDXIQwOPdU", "DmzZPgTh7_M",
  "Lst4MvxPCx4", "YkIBYppBtro", "3RyCldrCxL8", "1_-cZz8YRFw", "kMc_kat7YLE", "_GEMrEWCiXw", "sMgbjxyrgqw",
  "beh0v5Odn6g", "V45jIC4RthQ", "m-m2wMW4020", "EFJZ2l5Rc10", "YxglvjuoMZI", "T3I8r_NU2Wk", "3HytZ8tSiYE",
  "ApX7lGnn-2U", "LOsAzhRwUIk", "05wF2qqUVnI", "FoTH9BWP2gg", "Yf4Pld6UEdg", "h5Cvb_ZXnJc", "hPALIQJXMFg",
  "0va0izWG0Hc", "mgfhxq9bn8Q", "93evJf7Il-c", "7lggUuJtZXY", "8CgS_ANm26Y", "9-NMv5E-18s", "QAnRefsK-3Y",
  "VbT9vgs06Gc", "cy7L7ru37HE", "pR7zkayrXn8", "sO6_webPTdg", "zPsun8EkA2s", "8RbRpbaCh1I", "E9BYLwkGel8",
  "HpoWKtIcTcw", "YEPXAy-jyVo", "c_w5JbP_N90", "dd1OcfbBTh4", "fuTnlIafdLY", "i4DQFbs_RKU", "sOv9ISMIRQ0",
  "sQkhrJ3C49w", "s4cOjzTWGh8", "Q_CMuXKuvoU", "bF6kr28QHJc", "inL9r7ffQ7c", "36rdT1bFOk0", "4HRL8IxADhg",
  "BLvi5n274XY", "YZaEmcxvYvc", "bHd9dYS6UiU", "cqvwOx5baxM", "dQw77H27GMY", "hfOFmTBWTSQ", "1e0yk20hF7Y",
  "453IrXoe_Ug", "5TbaZA522Fs", "5ia1FNUN6fk", "AQUZcU5L9xE", "HLTISkkGbUI", "MuxETIn04F8", "1cs5nliQUSQ",
  "NMjYsvaOOQM", "NdmpvgZI4II", "WWIURef-J3s", "WhYY6IKaiVI", "WkkKW_mbWQI", "Yfi6-_lYa58", "_-P-9fe5U_4",
  "bVcY8fIlDa4", "mAG-Q4DZ5Zs", "nHDXMZLLQyY", "nxfjPX2qD_U", "o6X1TVEFHAY", "owC8E_G2fY4", "smrj15-QOAI",
  "tMaJzikpfeY", "tOi1Ho5Kwhk", "y2ZgKdt4Cj0", "16UXpd5BstM", "2JL1ZgMS7nY", "3qEON3iXjNM", "5hOsWGYAHFg",
  "8KaPqYLRWjc", "9id3ygnEhh8", "FYQHXDtlYX4", "LKM-M3C8Tv4", "SyT0Jx-ZT2g", "U6pcGCyOYwo", "UpeaTtqs7Oc",
  "aqpjV4cSJBI", "cvREfQLxC6k", "nsWiuQDzAw4", "pomBCVpfFNw", "rnp4upHkaqQ", "vmm8-Vqr8GQ", "wZ9FcYgjbPM",
  "J81diFHJqWw", "hF3NZH-UX0Y", "QexlGYK0DI4", "d3pf-MPqRKY", "xTVHvMHakow", "EyIJaL1sfpc", "1GLc7XE0Yvw",
  "zO8tQkjCpyc", "FSxiSEV1iPY", "kyEL8OTZwBk", "N0EoDEdWKA4", "EBBd2MOeOIU", "txmjnRTgB4Y", "09d8aVgYOqQ",
  "8XUuSO6eV7s", "SJcLsbR7ccQ", "_laoTHp0JWw", "dYCLRvvEnVA", "gRaAmM9ehzI", "kB9lSN4nORo", "kf-IuHxVN7g",
  "dj9ymEytgS0", "uPm6kDwrjSY", "yc-Qs4eiZ2U", "Ip7C7KJBxBk", "LpX01AXN5iM", "LrMyaDh_MSo", "53Jzhrf-IWk",
  "ALXWHiS-ing", "GWiiejeyAR8", "LYm7oczfWEk", "OnAAtrwsfOc", "QpmmGqGoo-8", "UuPdfdrvpdQ", "cD6Wi47E0hk",
  "xFQSF6GzQXQ", "eumRL5DfFzM", "fYhbxU61wuI", "mvSrmuOyRYQ", "zyUzxY37YVA", "lDqwgw-vYWc", "xsJwbk_N-RE",
  "8IScMLY_yLY", "H9A7Olg_QCo", "WyRSqoqHWF0", "XmkNwgkMC3U", "gPkOSEdG0OA", "0Fa4Wyv0GOk", "zpuRES7Fnm8",
  "PNH5hdUnXks", "LpqjenfvWzQ", "5qA5ibrq9NU", "GQZ7A4fvts4", "tAFtaCF5a30", "19EEFd2ueiI", "GICjcQQ0aM0",
  "IjZkoyk7T14", "co3N4y-RQKQ", "k1qCouxaNjQ", "VrPi2RUUXq4", "1WgqAO8AmsY", "F9Vo4fezmcE", "Gw4Ng9FKJyY",
  "PxTeZh0w1Go", "Q6VqxNlagpQ", "XsbGYVBY92c", "glXpHbwhQA4", "mJOReEqkgMM", "0Spa0u4IyLE", "1jLbPyOnpjo",
  "IaOyZ0KPlUU", "j7EZJwH8uCM", "na0fqtqARVs", "-4qvpm4Rd6Q", "8xJampnp9qc", "ACvOem_B-Ek", "AK435vKMtlo",
  "HtmLQkxj8ec", "MmiI3xo5Ju4", "OzKHRjr8nt8", "WlIW6LkFLp4", "jGG6-a4IrNw", "kNMpaK6SIbc", "p3eCPcvhsjM",
  "qIsZ9oxvWeI", "tBKVwXEzl0c", "umD1vXG7WIA", "3InKt2QjqQ8", "8Xy8xsLIgAU", "OaTrIaFLG6M", "TIZ3yFQCFfA",
  "XS9EXhxRbi8", "fzfhimnVghE", "y-C_8_p_F5w", "F0kz4L2wB2A", "pQ7yAREnJaw", "R7N_Bf14f0o", "uAPvGyjkrB8",
  "FSwSt1omSD8", "y9iL10DPhzI", "zs_JKa0cVsY", "rux7GLCqLWQ", "OWXe9v7PHDs", "5xxp7L-Ktp8", "_xRxSiooRnE",
  "NWrTrDIQ9XE", "Nq8BntIZb40", "UKYZ4NtUMTw", "jK7-PPBXwr4", "JRX5W9AhWoA", "n3UBbCXJaJ0", "tCWfCISvo5k",
  "D9obnqNB4aI", "XK2Wna2YG6Y", "LGkdzRl08vo", "cESK2Fb3Aq0", "3EqnSkAzfIg", "oSAPs1YDkq0", "j66VV2XKBJk",
  "rKoXeKg0y1Q", "-4wCvcPrX-E", "h5XzWxcWrtU", "uA7E_SUdtM8", "WtRGXnnGiVE", "Vl55gfNrZmM", "pTnEtB8mcVA",
  "tLNsDEp-JcA", "4LIZkNHlNaM", "38-NgBAet1c", "odNtpKqbCQo", "nen-DB_tz4M", "pmSPHJfg3AU", "uNkgwv4dqEs",
  "OZiElH5pKmo", "X1mtpheWDhs", "-YQLpNmH0MQ", "-0O6WmxU3pw", "N8aw4NAR62c", "vGWM3R_ihxI", "UgQV_5FjPNk",
  "OuDAdSnFtbw", "z3fSeC_oG-s", "RkLY_uJL0xc", "21SEb5M9IRs", "u5JpxwG34bE", "qajcmg64VNI", "mpLJPUifTNA",
  "Ba-hG3SGdfw", "VP9mfCJBX_Y", "AHbh4mzrwUQ", "ULID4U_e3TU", "G1fWNIazj5U", "vhLVeSDWB5M", "XhV7FuKtZnY",
  "ELiB_UwCVTY", "5daxvIoDLVU", "0YfmJqftSLE", "pTw6RbHzm-U", "K2yXX6uhGFE", "_fi53IYfitg", "xFyfHBkyQgA",
  "HTcbWPN1xxY", "rPfK6DcC1Vw", "JLN3i1y6_Dk", "Ejcq9mNGJk0", "XFZOr_5-0F0", "1oHlA7FtsGM", "dDyJNwNUbJs",
  "o_J7uas-9U0", "qj6ZFtvViic", "0m64VFmniGI", "ve_KEcn9Ues", "M6MJzzFKoPg", "HfS2relUTFg", "Maa5lwwHNrU",
  "x1KyU5MVHu4", "uSAO5p0GIU8", "RGFI6v2Biq0", "Vz_fn9o_Meo", "leypd9opVSc", "0poMFCoAhkM", "4Fjf6IQsjQs",
  "8Lp2qPXYix4", "E-LCT0YEpWQ", "Eznp9NU0Y4I", "HZIuHUGmnGY", "R0bGNxoJ4sM", "V1IuTlEU1ic", "VOOf2kQpeMw",
  "WfiHrS5Kjj8", "a3sAeqXrCYI", "cz_i2AsxGv0", "md0y8j1SxBk", "nD0_yE8Yy64", "oqacXWT14ic", "sCCLfLa0gyw",
  "40tIgtC8yec", "9XbV4ubs3Fw", "BtXOk3KUBd0", "ClbKAXVvzzo", "E5FJYDruwjs", "SAt-D1YFM1Q", "U4lCthMt9oY",
  "gLXqxcsF1dw", "n_6eC35_wzA", "r3iE2gDwIEk", "rxz4w8fxXZ8", "xNzBwpLBtSs", "zDOS3wCWea8", "4QL5Djtikmw",
  "5RcKCxfLEHM", "7L2scLHOEC4", "Hdr5IXNmRUE", "Nq2VYAIQyCs", "XcE2G9J8U_4", "qiba4m7wUXQ", "R3ZRYoTxhUE",
  "XEFWnanCtk8", "lZTaw-5V_mc", "DBUJH5f6rjU", "ECFRWVY8SGY", "Lm-5gKTKD7Y", "UDr00laBiYo", "T_SFXvO7ymc",
  "CKBwY7odu1E", "Wua3xtO-oys", "ds6FM6QEDWM", "fYLwmDCmJ0A", "fiABnex9O6Y", "nlimcAFzAQE", "LZQ4PvoArC8",
  "Qu5IQo0ghbs", "WOKBogNTmPI", "YguId6pF5KI", "c2oUDKf6ndo", "w2qbJB6ie9Y", "ZVraDQJ_I_Y", "l0bQZ9tnwvk",
  "BJfhRGjPznA", "beadZEtxtcs", "esrYgY--owE", "xnfQDhWWMkU", "O8iewlvGRN0", "WO_jh3zPTr0", "hLg4WPG4ehE",
  "M6NGzhww27o", "jHsA3IlRCm4", "nj4mPBJsauQ", "avCLyAi9DeY", "omDPxlDqDs0", "_KtWOkUsy1w", "PoNEyybToU4",
  "v58RteTeBlE", "susUKIwVD34", "MAwd31cafVg", "Y7p7jHP0Ii0", "GsEMHzvDq5M", "DjybU3_lUnc", "dkV4Dl3jfLs",
  "SKII-krCBcg", "-dzlXEIkqkI", "zPrI0q34qw8", "CfkyO8rGn2Y", "LzPKkAnAtjk", "h1YFNFOogEM", "tix59qHbyrI",
  "vLCsNfcbWqs", "d_IIBZd-xAQ", "Ul_7NL6j2ZI", "qPKICCU7Wec", "z0iCoqwZE_U", "VO3fi1c9ids", "R_bZWZvU-r4",
  "AxlmYK0B9Yw", "EpReLy7g6WM", "HKjzpPlfvc8", "nsUkTKmx2dI", "9RkGiNC-jJA", "WQWVnrG-wX4", "wDaE92bNRNw",
  "RgE2ryZsE3s", "zXjwi5tTcno", "SDWivCDevfE", "ct7R4Em77NY", "v55cSB0foxM", "sboLTO_FUY4", "MIF1XIgr-IQ",
  "CvDkoctU5a4", "tl31QISheOc", "Ji7Zy_tDFQ4", "aIEw-1E9ays", "HCs6I_BNtxo", "Y7bp-LlC3CM", "CNn_cuQsBh0",
  "-i-QFyNg8Io", "X-m1fDzX5Rc", "BsiePkp9bAc", "wKYEvQZ03Po", "bSfYcWPgkpI", "1KnFnmU6NWw", "uz81-q_o5LI",
  "6SGdA1xnd4A", "We6ENmiSSwI", "2X0BCy1bRcU", "H4paK9NPSoc", "6yHWS32aNOs", "OLPF727ETSg", "6YexvWyPC6k",
  "vZGe4g66rw4", "mz8Mb0MvBz4", "G_soqEsZRU8", "roc7MPff-C8", "KN0XZBa7K4Y", "QlHMnyKYYoI", "f-IpkGOOzYU",
  "OoH2peWBDEY", "a_qokyTjobo", "mS3cZvd1AvQ", "O4c1bnnwSzU", "UodtrfOmNh4", "gqN5tl1Kwpg", "jEg3pQmKBIw",
  "3OjpANs8PDw", "XzS56RqIxeE", "qDQ1JxqWcT8", "Gae2J6ExMsY", "R5jh4Ss4fKA", "7UuDjBiHrMA", "wzb6s4oJX1Y",
  "JsTTRgk_8Hc", "IbOoMlXlzjY", "DnllMgFybyQ", "_KQTdkGrw6A", "c32xomNzUIs", "lmNVJBc1Zoo", "phMVQUn1Sns",
  "pk4MA5aOSOY", "zlxVrlARMEI", "gQv87W3mAu8", "H7N4PSoJZMU", "EThkIHrfXWo", "CnCcYyJ8NTo", "EwwciE_mxo8",
  "a78n3v1aDMg", "u3xrPJu51SM", "tGvaofifDzI", "8n4-3zJSZyI", "pJXS28Odaqs", "Mrngwfko5kk", "Hfj0c6-vUiY",
  "-wAUE5rcxis", "vrXmfCUvigs", "rY83MZu--ck", "Gv3w2uNCo2o", "s-In3a1CAoI", "rRs__D_3mKY", "sZXuNv0L8YA",
  "88NOQTz5_yI", "dEZ1P72hmLg", "MX7tos4L1jQ", "dwOK83_n6_4", "Ln-4oxqStJI", "4rZDc-SaOB8", "GaSK6rscIgA",
  "dR7olu353VY", "mQ_qPqsc-i0", "1p0EnoA2u6o", "QeRsbucrii4", "Oy-j2w6haoA", "mB83CObqvhU", "jRI007mQ2Wo",
  "RMpAflHYP2g", "GBlHpCkYYgc", "DqUafRyXy_0", "W_KHgnxTHaY", "4eV8OvVEm6A", "AwDC-VZWfzU", "wjgYeizZwN8",
  "A6vBcCd_54I", "Pd42WwNAr8g", "aVqDALcqpII", "f8iC_C6rop0", "uIknA-azXKQ", "-vboUHsZ2KM", "A0edLNr-mks",
  "YtkxNkrfJWg", "9kSjk8uqNbI", "COmWEGiu9Hg", "Khxy7onLOnE", "s0p8jSaZOGc", "WLN80D-u2us", "Ez7hzMHEs2I",
  "3_SHb2rvvvI", "r3VajKBFhbA", "7i_LOcXlznQ", "fjekLTmR3ms", "O4YQRVeyl6I", "Q6q7MaVu9Dk", "L4876a9aakw",
  "vcvE5YpOjL4", "Ud5UpU0bvjw", "1imcyoNUO-A", "2RES9QrbVMA", "7BLsD_meNzw", "9wm4ey4OX8g", "9yaEGbPIxPk",
  "B9LZcfD-blU", "GTLqZPVojgI", "szJ7uDYHJ1Y", "2U2GS7IkE8c", "LLhU1ptXDp0", "OrydPLvNKmI", "TN9W-Jc7qZc",
  "rXkyO0fOOLE", "Rdm6ZwxZ3m4", "KB_rdqB-sVw", "izjxTA_-mNs", "liMBvMgSPC8", "-LK01oo7MAw", "P6gff20GmPQ",
  "COC9vdjMTlc", "TqxxCYnAxo8", "UlOt31lBhLY", "VAMJEgwaPEc", "AR0r8B6Ga8E", "vARTudIEq30", "nwQaU-agzFE",
  "hUmlujE6SN0", "RAOQ3ZubQGM", "0z-IZ2ar4eA", "WIUa93sXmPw", "sCiK7ABPcrw", "VxJWAmiYu_0", "rGcNJ_Nsuy8",
  "STlEq16n8kI", "NFlAszNFZdQ", "btbKcsb9Dzw", "zQjrjEYPsB8", "eozUm89Kk9k", "f0mxoBD9Fno", "O-6f5wQXSu8"
]

# Attempt failed/private/deleted ones too — most will return nothing, but some may have recovered
FAILED_IDS = [
  "fj2_d2lNGVk", "O1VkNuEChD4", "IGryscyFmV8", "0ypG1mlekNY", "owXqW04b08o", "M8XASiz30oE", "JRlaAip4kmk",
  "qtG8c2zhn7A", "Gt3o8lcbcII", "cI7D2aO34yw", "w1gF90_cBl4", "ZGvKY4mPfIc", "GfAMCHC6_ek", "CZ_r5sYeTyY",
  "obK5uqYXOJU", "bSyewSnu2Ak", "mNM-x9RFMcE", "207izZBbqVg", "1w-IStuMl3M", "M7ItOHTrvz8", "UJM00IqGKtc",
  "K-AFDVOkIoE", "1nhXsnx5--Y", "NJQ573JDmAg", "RBb_3sgOgFY", "ffhDTzE4nDU", "uZg9XnRub7w", "RFx74Q6Oq2c",
  "9Mv4Thnx9SU", "Gdd-5uWUW5w", "dqUq_a0DyLs", "1PlGMOAypCI", "QzJ_Ft1de1o", "Mr1cjAz2y9I", "HELtP96Dd4w",
  "cHAJiF2byzg", "vch9C_hNjGs", "k8iO5daXllM", "ftFDBaH7RFg", "pPHQMD3w9-s", "Fbd7ln2i9dw", "PslFhdZaBFA",
  "AviNwtN1luo", "oaKWpxmu0YI", "nUrc8O7Avvk", "6-GWHR9_iSU", "Qr_pw4E-REk", "V2WQ20Ocw_o", "BkM7IcqUaj0"
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
        chunks = [" ".join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]
        restored = []
        for idx, chunk in enumerate(chunks):
            try:
                restored.append(_punct_model.restore_punctuation(chunk))
            except Exception as ce:
                print("    ⚠️  BERT chunk {}/{} failed: {} — using raw".format(idx + 1, len(chunks), ce))
                restored.append(chunk)
        return " ".join(restored)
    except Exception as e:
        print("    ⚠️  BERT restore failed: {} — using raw text".format(e))
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
            "TRANSCRIPT:\n{}\n\nCORRECTED TRANSCRIPT:".format(text)
        )
        payload = json.dumps({
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}]
        }).encode("utf-8")

        req = _urllib_req.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type":      "application/json",
                "x-api-key":         ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        with _urllib_req.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        return result["content"][0]["text"].strip()
    except Exception as e:
        print("    ⚠️  Claude API restore failed for {}: {} — using raw text".format(video_id, e))
        return text


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
        "raw YouTube transcript. Fix sentence boundaries. Do NOT change any words, "
        "remove content, or add explanations. Return only the corrected transcript text.\n\n"
        "TRANSCRIPT:\n{}\n\nCORRECTED TRANSCRIPT:".format(text)
    )

    max_retries = 5
    backoff_factor = 2.0
    initial_delay = 1.0

    for attempt in range(max_retries):
        try:
            client = OpenAI(
                base_url="https://integrate.api.nvidia.com/v1",
                api_key=NVIDIA_KEY
            )
            completion = client.chat.completions.create(
                model="meta/llama-3.1-70b-instruct",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                top_p=0.7,
                max_tokens=2048,
                stream=True
            )
            restored = []
            for chunk in completion:
                if chunk.choices and chunk.choices[0].delta.content is not None:
                    restored.append(chunk.choices[0].delta.content)
            return "".join(restored).strip()
        except Exception as e:
            delay = initial_delay * (backoff_factor ** attempt)
            print("    ⚠️  NVIDIA API attempt {}/{} failed for {}: {} — retrying in {:.1f}s...".format(
                attempt + 1, max_retries, video_id, e, delay))
            if attempt < max_retries - 1:
                time.sleep(delay)
            else:
                print("    ❌ All {} NVIDIA API attempts failed for {} — using raw text".format(max_retries, video_id))
                return text
    return text


def restore_punctuation(text, video_id=""):
    # type: (str, str) -> str
    """
    Three-tier punctuation restoration:
      PUNCT_MODE = "nvidia" → NVIDIA API (Llama-3.1-70b-instruct)
      PUNCT_MODE = "auto"   → BERT → Claude fallback
      PUNCT_MODE = "bert"   → BERT only
      PUNCT_MODE = "claude" → Claude API always
      PUNCT_MODE = "none"   → return as-is
    """
    if not text or PUNCT_MODE == "none":
        return text

    if PUNCT_MODE == "nvidia":
        print("    🤖 Restoring punctuation via NVIDIA API...")
        return _nvidia_restore(text, video_id)

    if PUNCT_MODE == "claude":
        print("    🤖 Restoring punctuation via Claude API...")
        return _claude_restore(text, video_id)

    if PUNCT_MODE == "bert":
        if not BERT_PUNCT_AVAILABLE:
            print("    ⚠️  BERT model unavailable and PUNCT_MODE='bert' — skipping.")
            return text
        return _bert_restore(text)

    # PUNCT_MODE == "auto" (default)
    if BERT_PUNCT_AVAILABLE:
        return _bert_restore(text)
    else:
        print("    🤖 BERT unavailable — restoring punctuation via Claude API...")
        return _claude_restore(text, video_id)


# ── Noise patterns to strip from raw captions ─────────────────────────────────
# Covers: [Music], [Applause], [Laughter], [MUSIC], [ __ ], timestamps like (0:00)
_NOISE_PATTERNS = [
    re.compile(r"\[+[^\]]{0,40}\]+"),          # [Music], [Applause], [[Music]], [ __ ]
    re.compile(r"\(+[^\)]{0,20}\)+"),          # (music), (applause)
    re.compile(r"\d{1,2}:\d{2}(?::\d{2})?"),  # timestamps: 0:00, 1:23:45
    re.compile(r"♪+\s*.*?\s*♪+"),             # ♪ music notes ♪
    re.compile(r"<[^>]{0,30}>"),               # <inaudible>, HTML-like tags
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
    text = (text
            .replace("&#39;", "'").replace("&amp;", "&")
            .replace("&lt;",  "<").replace("&gt;",  ">")
            .replace("&quot;", '"').replace("\xa0", " "))

    # 2. Strip all noise patterns
    for pattern in _NOISE_PATTERNS:
        text = pattern.sub(" ", text)

    # 3. Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def write_md(video_id, title, channel, date, description, plain_text, language):
    # type: (str, str, str, str, str, str, str) -> Path
    try:
        url      = "https://www.youtube.com/watch?v={}".format(video_id)
        filename = OUTPUT_DIR / "{}.md".format(video_id)
        body     = plain_text if plain_text else "_No transcript available._"
        desc     = description if description else "_No description available._"
        content  = (
            "# {title}\n\n"
            "**Video ID:** `{vid}`\n"
            "**URL:** {url}\n"
            "**Channel:** {channel}\n"
            "**Published:** {date}\n"
            "**Language:** {lang}\n\n"
            "## Description\n\n{desc}\n\n"
            "## Transcript\n\n{body}\n"
        ).format(title=title, vid=video_id, url=url, channel=channel,
                 date=date, lang=language, desc=desc, body=body)
        filename.write_text(content, encoding="utf-8")
        return filename
    except Exception as e:
        print("    ⚠️  write_md failed for {}: {}".format(video_id, e))
        raise


def load_state():
    # type: () -> Dict
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print("⚠️  Could not load _state.json: {} — starting fresh.".format(e))
    return {"processed": [], "failed": []}


def save_state(state):
    # type: (Dict) -> None
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception as e:
        print("  ⚠️  Could not save state: {}".format(e))


def load_json():
    # type: () -> Dict
    try:
        if JSON_FILE.exists():
            return json.loads(JSON_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print("⚠️  Could not load transcripts.json: {} — starting fresh.".format(e))
    return {}


def save_json(data):
    # type: (Dict) -> None
    """Atomic write: .tmp → rename."""
    tmp = JSON_FILE.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(JSON_FILE)
    except Exception as e:
        print("  ⚠️  Could not save transcripts.json: {}".format(e))
        try:
            tmp.unlink()
        except Exception:
            pass


def run_batch(client, video_ids):
    # type: (ApifyClient, List[str]) -> List[Dict]
    """
    johnvc/YoutubeTranscripts input: { "youtube_url": [list of URLs] }
    Returns items with: video_id, non_timestamped, timestamped, language, success, url
    """
    urls = ["https://www.youtube.com/watch?v={}".format(v) for v in video_ids]
    try:
        run = client.actor(ACTOR_ID).call(run_input={"youtube_url": urls})
    except Exception as e:
        raise RuntimeError("Apify actor call failed: {}".format(e)) from e

    dataset_id = run.get("defaultDatasetId") if run else None
    if not dataset_id:
        print("  ⚠️  No dataset returned for batch: {}...".format(video_ids[:3]))
        return []

    items, offset = [], 0
    while True:
        try:
            page = list(client.dataset(dataset_id).iterate_items(offset=offset, limit=100))
        except Exception as e:
            print("  ⚠️  Pagination error at offset {}: {} — stopping.".format(offset, e))
            break
        if not page:
            break
        items.extend(page)
        offset += len(page)
    return items


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
        print("  ⚠️  extract_video_id error: {}".format(e))
        return None


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    # ── Pre-flight ─────────────────────────────────────────────────────────
    if not APIFY_TOKEN:
        print("ERROR: APIFY_API_TOKEN not set.")
        print("Fix : export APIFY_API_TOKEN='your_token_here'")
        sys.exit(1)

    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print("ERROR: Cannot create output dir '{}': {}".format(OUTPUT_DIR, e))
        sys.exit(1)

    try:
        client = ApifyClient(APIFY_TOKEN)
    except Exception as e:
        print("ERROR: Failed to init Apify client: {}".format(e))
        sys.exit(1)

    # ── Load state ─────────────────────────────────────────────────────────
    state            = load_state()
    transcripts_data = load_json()

    try:
        done_from_md = {p.stem for p in OUTPUT_DIR.glob("*.md")}
    except Exception:
        done_from_md = set()

    already_done = (
        set(state.get("processed", []))
        | set(state.get("failed", []))
        | set(transcripts_data.keys())
        | done_from_md
    )  # type: Set[str]

    # Deduplicate input list (preserve order)
    seen_ids = set()   # type: Set[str]
    all_ids  = []      # type: List[str]
    for vid in PENDING_IDS + FAILED_IDS:
        if vid not in seen_ids:
            seen_ids.add(vid)
            all_ids.append(vid)

    remaining = [v for v in all_ids if v not in already_done]

    print("─" * 60)
    print("📋 Total unique videos  : {}".format(len(all_ids)))
    print("✅ Already processed    : {}".format(len(already_done)))
    print("⏳ Remaining to fetch   : {}".format(len(remaining)))
    print("💰 Estimated cost       : ~${:.4f} USD".format(len(remaining) * 0.00012))
    print("🔤 Punctuation restore  : {}".format("ON" if USE_PUNCT else "OFF"))
    print("─" * 60 + "\n")

    if not remaining:
        print("Nothing to do — all videos already processed.")
        return

    batches    = [remaining[i:i + BATCH_SIZE] for i in range(0, len(remaining), BATCH_SIZE)]
    total_done = 0

    for batch_num, batch in enumerate(batches, 1):
        print("🔄 Batch {}/{} — {} videos...".format(batch_num, len(batches), len(batch)))

        # Live dedup guard
        batch = [v for v in batch if v not in already_done]
        if not batch:
            print("  ↳ All videos in this batch already done, skipping.")
            continue

        # ── Call Apify ─────────────────────────────────────────────────────
        try:
            results = run_batch(client, batch)
        except Exception as e:
            print("  ❌ Batch {} failed entirely: {}".format(batch_num, e))
            for vid in batch:
                if vid not in already_done:
                    state["failed"].append(vid)
                    already_done.add(vid)
            save_state(state)
            time.sleep(SLEEP_BETWEEN)
            continue

        returned_ids = set()  # type: Set[str]

        # ── Process results ────────────────────────────────────────────────
        for item in results:
            try:
                vid = extract_video_id(item)
                if not vid:
                    print("  ⚠️  Result with no video_id — skipping.")
                    continue
                if vid in already_done:
                    print("  ⏭️  {} — already done, skipping".format(vid))
                    continue

                returned_ids.add(vid)

                # johnvc returns a top-level "success" bool
                success = item.get("success", True)
                plain   = build_plain_text(item) if success else ""

                language = item.get("language", "unknown")
                lang_code = item.get("language_code", "")

                # Actor doesn't return title/channel/date — use video ID as title
                title   = item.get("title", vid)
                channel = item.get("channelName", item.get("channel", "Unknown Channel"))
                date    = item.get("datePublished", item.get("uploadDate", ""))

                if plain:
                    plain = restore_punctuation(plain)
                    try:
                        path = write_md(vid, title, channel, date, "", plain, language)
                        print("  ✅ {} ({}) → {}".format(vid, language, path.name))
                    except Exception as we:
                        print("  ⚠️  write_md error for {}: {} — saving to JSON only".format(vid, we))

                    state["processed"].append(vid)
                    transcripts_data[vid] = {
                        "videoId":       vid,
                        "title":         title,
                        "channelName":   channel,
                        "datePublished": date,
                        "language":      language,
                        "language_code": lang_code,
                        "is_generated":  item.get("is_generated", True),
                        "total_seconds": item.get("total_seconds", 0),
                        "captions":      plain,
                        "timestamped":   item.get("timestamped", []),
                        "url":           "https://www.youtube.com/watch?v={}".format(vid),
                    }
                else:
                    try:
                        write_md(vid, title, channel, date, "", "", language)
                    except Exception:
                        pass
                    reason = "failed/no captions" if not success else "empty transcript"
                    print("  ⚠️  {} — {} ".format(vid, reason))
                    state["failed"].append(vid)

                already_done.add(vid)

            except Exception as item_err:
                print("  ❌ Unexpected error on item: {}".format(item_err))
                print("     {}".format(traceback.format_exc().splitlines()[-1]))
                continue

        # ── Mark videos not returned by actor ─────────────────────────────
        for vid in batch:
            if vid not in returned_ids and vid not in already_done:
                print("  ❌ {} — not returned by actor".format(vid))
                state["failed"].append(vid)
                already_done.add(vid)

        save_state(state)
        save_json(transcripts_data)
        total_done += len(batch)
        print("  ↳ Progress: {}/{} | Sleeping {}s...\n".format(
            total_done, len(remaining), SLEEP_BETWEEN))
        time.sleep(SLEEP_BETWEEN)

    # ── Final summary ──────────────────────────────────────────────────────
    try:
        failed_unique = sorted(set(state.get("failed", [])))
        FAILED_FILE.write_text("\n".join(failed_unique), encoding="utf-8")
    except Exception as e:
        print("⚠️  Could not write _failed.txt: {}".format(e))
        failed_unique = []

    print("\n" + "=" * 60)
    print("✅ Successfully processed : {} transcripts".format(len(set(state.get("processed", [])))))
    print("❌ Failed / no captions   : {} videos".format(len(failed_unique)))
    print("💰 Total cost             : ~${:.4f} USD".format(
        len(set(state.get("processed", []))) * 0.00012))
    print("📁 Output:")
    print("   → {}".format(FAILED_FILE))
    print("   → {}".format(JSON_FILE))
    print("   → {}/*.md".format(OUTPUT_DIR))
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted — state saved, re-run to resume.")
        sys.exit(0)
    except Exception as e:
        print("\n❌ Fatal error: {}".format(e))
        print(traceback.format_exc())
        sys.exit(1)