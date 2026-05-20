#!/usr/bin/env python3
"""
AskMukthiGuru — Bulk YouTube Transcript Extractor
Uses Apify karamelo/youtube-transcripts actor in batches.

Usage:
    pip install apify-client
    export APIFY_API_TOKEN="your_token_here"
    python extract_transcripts.py

Output:
    ./transcripts/<video_id>.md  — one file per video
    ./transcripts/_failed.txt    — videos that returned no transcript
    ./transcripts/_state.json    — resumable run state
"""

import os
import json
import time
import re
import sys
from pathlib import Path
from datetime import datetime

try:
    from apify_client import ApifyClient
except ImportError:
    print("ERROR: apify-client not installed. Run: pip install apify-client")
    sys.exit(1)

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
APIFY_TOKEN    = os.environ.get("APIFY_API_TOKEN", "")
ACTOR_ID       = "karamelo/youtube-transcripts"
BATCH_SIZE     = 50        # videos per Apify run
SLEEP_BETWEEN  = 3         # seconds between batches (be polite)
OUTPUT_DIR     = Path("transcripts")
STATE_FILE     = OUTPUT_DIR / "_state.json"
FAILED_FILE    = OUTPUT_DIR / "_failed.txt"
TRANSCRIPTS_JSON_FILE = OUTPUT_DIR / "transcripts.json"

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

def clean_captions(raw: str) -> str:
    """Decode HTML entities and normalize whitespace."""
    raw = raw.replace("&#39;", "'").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    raw = re.sub(r'\s+', ' ', raw).strip()
    return raw

def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()

def write_md(item: dict, is_failed_attempt: bool = False) -> Path:
    """Write a single transcript to a .md file. Returns the path written."""
    video_id    = item.get("videoId", "unknown")
    title       = item.get("title", "Untitled")
    channel     = item.get("channelName", "Unknown Channel")
    date        = item.get("datePublished", "")
    description = item.get("description", "")
    captions    = item.get("captions", "")
    url         = f"https://www.youtube.com/watch?v={video_id}"

    captions_clean = clean_captions(captions) if captions else "_No transcript available (private/deleted video)._"

    safe_title = sanitize_filename(title)[:80]
    filename = OUTPUT_DIR / f"{video_id}.md"

    content = f"""# {title}

**Video ID:** `{video_id}`  
**URL:** {url}  
**Channel:** {channel}  
**Published:** {date}  

## Description

{description if description else "_No description available._"}

## Transcript

{captions_clean}
"""
    filename.write_text(content, encoding="utf-8")
    return filename

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"processed": [], "failed": []}

def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))

def load_transcripts_json() -> dict:
    if TRANSCRIPTS_JSON_FILE.exists():
        try:
            return json.loads(TRANSCRIPTS_JSON_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"⚠️  Could not load transcripts.json: {e}")
    return {}

def save_transcripts_json(transcripts: dict):
    TRANSCRIPTS_JSON_FILE.write_text(json.dumps(transcripts, indent=2, ensure_ascii=False), encoding="utf-8")

def sync_existing_md_to_json(transcripts_data: dict) -> dict:
    """Scan the transcripts output directory for any existing .md files and try to reconstruct
    their data to add them to transcripts.json if they aren't already present."""
    if not OUTPUT_DIR.exists():
        return transcripts_data

    modified = False
    for md_path in OUTPUT_DIR.glob("*.md"):
        video_id = md_path.stem
        if video_id == "README" or video_id.startswith("_") or video_id in transcripts_data:
            continue
        
        try:
            content = md_path.read_text(encoding="utf-8")
            title = "Untitled"
            channel = "Unknown Channel"
            date = ""
            description = ""
            captions = ""
            
            lines = content.splitlines()
            if lines and lines[0].startswith("# "):
                title = lines[0][2:].strip()
            
            desc_start = -1
            desc_end = -1
            trans_start = -1
            
            for idx, line in enumerate(lines):
                if line.startswith("**Channel:**"):
                    channel = line.replace("**Channel:**", "").replace("  ", "").strip()
                elif line.startswith("**Published:**"):
                    date = line.replace("**Published:**", "").replace("  ", "").strip()
                elif line.startswith("## Description"):
                    desc_start = idx + 1
                elif line.startswith("## Transcript"):
                    desc_end = idx
                    trans_start = idx + 1
            
            if desc_start != -1 and desc_end != -1:
                description = "\n".join(lines[desc_start:desc_end]).strip()
            if trans_start != -1:
                captions = "\n".join(lines[trans_start:]).strip()
            
            transcripts_data[video_id] = {
                "videoId": video_id,
                "title": title,
                "channelName": channel,
                "datePublished": date,
                "description": description,
                "captions": captions,
                "url": f"https://www.youtube.com/watch?v={video_id}"
            }
            print(f"  📝 Restored {video_id} from existing markdown file to transcripts.json")
            modified = True
        except Exception as e:
            print(f"  ⚠️ Could not parse existing md file {md_path.name}: {e}")
            
    if modified:
        save_transcripts_json(transcripts_data)
        
    return transcripts_data

def run_batch(client: ApifyClient, video_ids: list) -> list:
    """Run one Apify actor call for a batch of video IDs. Returns list of result dicts."""
    urls = [f"https://www.youtube.com/watch?v={vid}" for vid in video_ids]
    run = client.actor(ACTOR_ID).call(run_input={
        "urls": urls,
        "outputFormat": "singleStringText",
        "channelNameBoolean": True,
        "datePublishedBoolean": True,
        "descriptionBoolean": True,
        "proxyOptions": {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"]},
        "maxRetries": 5,
    })
    dataset_id = run.get("defaultDatasetId")
    if not dataset_id:
        print(f"  ⚠️  No dataset returned for batch: {video_ids[:3]}...")
        return []

    items = []
    offset = 0
    while True:
        page = list(client.dataset(dataset_id).iterate_items(offset=offset, limit=100))
        if not page:
            break
        items.extend(page)
        offset += len(page)
    return items

def main():
    if not APIFY_TOKEN:
        print("ERROR: Set APIFY_API_TOKEN environment variable.")
        sys.exit(1)

    OUTPUT_DIR.mkdir(exist_ok=True)
    client = ApifyClient(APIFY_TOKEN)
    state  = load_state()
    transcripts_data = load_transcripts_json()

    # Sync any pre-existing md files into transcripts.json
    transcripts_data = sync_existing_md_to_json(transcripts_data)

    already_done = set(state["processed"] + state["failed"] + list(transcripts_data.keys()))
    all_ids      = PENDING_IDS + FAILED_IDS
    remaining    = [vid for vid in all_ids if vid not in already_done]

    print(f"📋 Total unique videos : {len(all_ids)}")
    print(f"✅ Already processed   : {len(already_done)}")
    print(f"⏳ Remaining to fetch  : {len(remaining)}")
    print(f"💰 Estimated cost      : ~${len(remaining) * 0.007:.2f} USD\n")

    if not remaining:
        print("Nothing to do — all videos already processed.")
        return

    batches     = [remaining[i:i+BATCH_SIZE] for i in range(0, len(remaining), BATCH_SIZE)]
    total_done  = 0
    newly_failed = []

    for batch_num, batch in enumerate(batches, 1):
        print(f"🔄 Batch {batch_num}/{len(batches)} — {len(batch)} videos...")
        try:
            results = run_batch(client, batch)
        except Exception as e:
            print(f"  ❌ Batch {batch_num} failed entirely: {e}")
            newly_failed.extend(batch)
            state["failed"].extend(batch)
            save_state(state)
            continue

        returned_ids = {r.get("videoId") for r in results}

        for item in results:
            vid = item.get("videoId")
            if not vid:
                continue
            if item.get("captions") or item.get("transcript"):
                path = write_md(item)
                print(f"  ✅ {vid} → {path.name}")
                state["processed"].append(vid)
                
                # Add to transcripts.json
                captions = item.get("captions") or item.get("transcript") or ""
                transcripts_data[vid] = {
                    "videoId": vid,
                    "title": item.get("title", "Untitled"),
                    "channelName": item.get("channelName", "Unknown Channel"),
                    "datePublished": item.get("datePublished", ""),
                    "description": item.get("description", ""),
                    "captions": clean_captions(captions),
                    "url": f"https://www.youtube.com/watch?v={vid}"
                }
            else:
                write_md(item, is_failed_attempt=True)  # write stub
                print(f"  ⚠️  {vid} — no transcript (private/deleted)")
                state["failed"].append(vid)

        # Mark videos the actor didn't return at all
        for vid in batch:
            if vid not in returned_ids and vid not in state["processed"] and vid not in state["failed"]:
                print(f"  ❌ {vid} — not returned by actor")
                state["failed"].append(vid)

        save_state(state)
        save_transcripts_json(transcripts_data)
        total_done += len(batch)
        print(f"  ↳ Progress: {total_done}/{len(remaining)} | Sleeping {SLEEP_BETWEEN}s...\n")
        time.sleep(SLEEP_BETWEEN)

    # Write failed list
    failed_unique = list(set(state["failed"]))
    FAILED_FILE.write_text("\n".join(failed_unique))

    print("\n" + "="*60)
    print(f"✅ Successfully written : {len(state['processed'])} transcripts")
    print(f"❌ Failed / no captions : {len(failed_unique)} videos → {FAILED_FILE}")
    print(f"📁 Output directory    : {OUTPUT_DIR.resolve()}")
    print("="*60)

if __name__ == "__main__":
    main()