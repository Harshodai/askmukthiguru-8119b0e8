# Seeded 50 Served Clips Human Label Sheet

**Sampling Configuration:** Seed = 42, deterministic pseudorandom sample over verified `first_person_v10` points.
**Invariant:** Quote text is NEVER modified, extracted, or duplicated in this sheet. Reviewers verify speaker identity and clip coherence directly from audio.

## Human Verification Protocol

1. For each clip, click the provided YouTube link starting at `start_seconds`.
2. Confirm that the voice matches the declared teacher (`sri_krishnaji` or `sri_preethaji`).
3. Check for boundary cuts (e.g. cut mid-thought or joined sentences).
4. Record verdict: `PASS`, `FAIL_SPEAKER`, `FAIL_BOUNDARY`, or `UNSURE`.

## Sampled Verification Table

| # | Point ID | Video ID | Start ms | End ms | Window | Teacher | Audio Link | Voice Match | Boundary Clean | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `0045104c-0af1-565b-bcb5-98b91ef223f8` | `IjZkoyk7T14` | 66240 | 76160 | 66s–76s | `preethaji` | [Listen](https://www.youtube.com/watch?v=IjZkoyk7T14&t=66s) | `PASS` | `PASS` |  preethaji is asking people to join manifest a program, so we can remove this and keep the before point of video, may be we can ask users to register for manifest  |
| 2 | `00b5a51f-7250-5f2a-abad-11e4a7f22114` | `2DLb6hDIhmg` | 160500 | 238480 | 160s–238s | `preethaji` | [Listen](https://www.youtube.com/watch?v=2DLb6hDIhmg&t=160s) | `PASS` | `FAIL_BOUNDARY` | because this is a story continuation as per the previous point, it would be better if we can serve both or entire story that preethaji here explaining at a single time |
| 3 | `00c475c4-14c5-5f09-beca-06d79b278c44` | `_GEMrEWCiXw` | 604350 | 757930 | 604s–757s | `krishnaji` | [Listen](https://www.youtube.com/watch?v=_GEMrEWCiXw&t=604s) | `PASS` | `FAIL_BOUNDARY` | continuity is missing before and after |
| 4 | `00d2acb5-e6d3-5dff-9dc3-6ff06335c0ee` | `vcvE5YpOjL4` | 59440 | 76000 | 59s–76s | `krishnaji` | [Listen](https://www.youtube.com/watch?v=vcvE5YpOjL4&t=59s) | `PASS` | `FAIL_BOUNDARY` | because this is a story continuation as per the previous point, it would be better if we can serve both or entire story that krishnaji here explaining at a single time |
| 5 | `00ecb926-9f5d-5ce4-b115-f04d57e25c31` | `Fn62UQTIMEk` | 770 | 16770 | 0s–16s | `preethaji` | [Listen](https://www.youtube.com/watch?v=Fn62UQTIMEk&t=0s) | `PASS` | `FAIL_BOUNDARY` | I feel if this is a video ingested would be better |
| 6 | `034687a3-4a64-5219-8262-5be89e8a218c` | `v58RteTeBlE` | 108610 | 139970 | 108s–139s | `preethaji` | [Listen](https://www.youtube.com/watch?v=v58RteTeBlE&t=108s) | `PASS` | `FAIL_BOUNDARY` | |
| 7 | `03922e5d-ad6b-5d2c-b696-ab12fcb3faca` | `YZaEmcxvYvc` | 50720 | 62320 | 50s–62s | `preethaji` | [Listen](https://www.youtube.com/watch?v=YZaEmcxvYvc&t=50s) | `PASS` | `PASS` | because preethaji is asking people to join Field of awakening a program, keep the before point of video of the video if this reasonates the same with the user, but we need to be careful since we should not give everytime a session registration |
| 8 | `03cde63d-1c1f-5be1-95f9-163a712e1318` | `M7ItOHTrvz8` | 46000 | 215990 | 46s–215s | `krishnaji` | [Listen](https://www.youtube.com/watch?v=M7ItOHTrvz8&t=46s) | `PASS` | `PASS` | |
| 9 | `03f24c38-d355-52d2-bf5f-fadc9838402f` | `2X0BCy1bRcU` | 12640 | 38560 | 12s–38s | `preethaji` | [Listen](https://www.youtube.com/watch?v=2X0BCy1bRcU&t=12s) | `PASS` | `FAIL_BOUNDARY` | this is also for a course registration, may be we can ask users to check this at the end and give the other parts of this video |
| 10 | `044c708e-6680-518a-9e86-b283f5dd873d` | `EhY6npcnSs8` | 50630 | 80390 | 50s–80s | `preethaji` | [Listen](https://www.youtube.com/watch?v=EhY6npcnSs8&t=50s) | `PASS` | `FAIL_BOUNDARY` | |
| 11 | `05f0dbf7-96c4-5941-b41a-6f7cc232d19a` | `mz8Mb0MvBz4` | 9840 | 18000 | 9s–18s | `preethaji` | [Listen](https://www.youtube.com/watch?v=mz8Mb0MvBz4&t=9s) | `PASS` | `FAIL_BOUNDARY` | |
| 12 | `0751dc9b-37a9-57f7-9fbd-e96a881973e7` | `sMgbjxyrgqw` | 79920 | 104680 | 79s–104s | `krishnaji` | [Listen](https://www.youtube.com/watch?v=sMgbjxyrgqw&t=79s) | `PASS` | `PASS` | this is best for one shot answers but if the users asks for more, we might not get |
| 13 | `07866498-b6bc-5d98-9f84-54937bf3f775` | `FSwSt1omSD8` | 39520 | 49760 | 39s–49s | `preethaji` | [Listen](https://www.youtube.com/watch?v=FSwSt1omSD8&t=39s) | `PASS` | `FAIL_BOUNDARY` | |
| 14 | `09253b38-f7aa-5345-be08-a6a639673426` | `Ao8Rhhl9E8k` | 259779 | 275300 | 259s–275s | `preethaji` | [Listen](https://www.youtube.com/watch?v=Ao8Rhhl9E8k&t=259s) | `PASS` | `FAIL_BOUNDARY` | |
| 15 | `0a8d0a07-105c-5a77-aedb-3b07e052816b` | `kMc_kat7YLE` | 676860 | 707260 | 676s–707s | `krishnaji` | [Listen](https://www.youtube.com/watch?v=kMc_kat7YLE&t=676s) | `PASS` | `FAIL_BOUNDARY` | not a good way of storing data because it is not continous |
| 16 | `0ad56deb-43e1-594b-88ac-37cadea0aa00` | `Lm-5gKTKD7Y` | 104610 | 130080 | 104s–130s | `krishnaji` | [Listen](https://www.youtube.com/watch?v=Lm-5gKTKD7Y&t=104s) | `FAIL_SPEAKER` | `FAIL_BOUNDARY` | this is an experience shared by a devotee and not full |
| 17 | `0ad9693a-32ea-5af1-8b23-8c045a841f8b` | `TqxxCYnAxo8` | 715480 | 761000 | 715s–761s | `preethaji` | [Listen](https://www.youtube.com/watch?v=TqxxCYnAxo8&t=715s) | `PASS` | `FAIL_BOUNDARY` | I feel if the before and after pieces are joined together so that we can give users a better part |
| 18 | `0af96626-378f-58b6-85ee-2fb4037a56c7` | `pTnZt0SqDFM` | 123540 | 132500 | 123s–132s | `preethaji` | [Listen](https://www.youtube.com/watch?v=pTnZt0SqDFM&t=123s) | `PASS` | `FAIL_BOUNDARY` | there is still completion present |
| 19 | `0b1daf8b-d954-5fe9-b756-e9b898e78435` | `ajMAwlKh3YM` | 83600 | 127520 | 83s–127s | `preethaji` | [Listen](https://www.youtube.com/watch?v=ajMAwlKh3YM&t=83s) | `PASS` | `UNSURE` | it is not complete |
| 20 | `0bf0b2bd-eebe-50ac-8f2e-0394783e695a` | `HKjzpPlfvc8` | 101390 | 113470 | 101s–113s | `krishnaji` | [Listen](https://www.youtube.com/watch?v=HKjzpPlfvc8&t=101s) | `PASS` | `FAIL_BOUNDARY` | |
| 21 | `0cecf59d-be92-5621-8364-2eea0244aed5` | `GfAMCHC6_ek` | 25280 | 68080 | 25s–68s | `krishnaji` | [Listen](https://www.youtube.com/watch?v=GfAMCHC6_ek&t=25s) | `PASS` | `PASS` | |
| 22 | `0d246bd3-3197-589e-acfc-820ff22e9e79` | `JRlaAip4kmk` | 571720 | 620446 | 571s–620s | `preethaji` | [Listen](https://www.youtube.com/watch?v=JRlaAip4kmk&t=571s) | `PASS` | `FAIL_BOUNDARY` | |
| 23 | `0f72ae08-036c-5528-8b64-e4e36c53ae11` | `h5XzWxcWrtU` | 177150 | 249150 | 177s–249s | `krishnaji` | [Listen](https://www.youtube.com/watch?v=h5XzWxcWrtU&t=177s) | `PASS` | `PASS` | |
| 24 | `0fc844ee-e4b7-5db7-b55d-2a5eedc5d6dd` | `UlOt31lBhLY` | 836120 | 859720 | 836s–859s | `preethaji` | [Listen](https://www.youtube.com/watch?v=UlOt31lBhLY&t=836s) | `PASS` | `FAIL_BOUNDARY` | |
| 25 | `10a3f933-1e18-576d-9870-a42a6219c3c0` | `L4876a9aakw` | 16160 | 32800 | 16s–32s | `krishnaji` | [Listen](https://www.youtube.com/watch?v=L4876a9aakw&t=16s) | `PASS` | `FAIL_BOUNDARY` | |
| 26 | `11571cb7-85be-56a3-a5b7-a3e34029f5da` | `Z7w7soyXmHs` | 38520 | 129400 | 38s–129s | `preethaji` | [Listen](https://www.youtube.com/watch?v=Z7w7soyXmHs&t=38s) | `PASS` | `FAIL_BOUNDARY` | |
| 27 | `13138aed-6824-56dc-98c3-f5eb2f1aa757` | `Ip7C7KJBxBk` | 58383 | 71790 | 58s–71s | `preethaji` | [Listen](https://www.youtube.com/watch?v=Ip7C7KJBxBk&t=58s) | `PASS` | `FAIL_BOUNDARY` | |
| 28 | `131e755f-0efa-5ac3-83d7-a0ca3642299c` | `1imcyoNUO-A` | 126560 | 149440 | 126s–149s | `krishnaji` | [Listen](https://www.youtube.com/watch?v=1imcyoNUO-A&t=126s) | `PASS` | `FAIL_BOUNDARY` | not complete |
| 29 | `145aeae3-842e-5ecb-bb21-d3b7d706f258` | `owXqW04b08o` | 304852 | 372320 | 304s–372s | `preethaji` | [Listen](https://www.youtube.com/watch?v=owXqW04b08o&t=304s) | `PASS` | `FAIL_BOUNDARY` | this is a prayer |
| 30 | `171c5fa3-89ff-560c-872a-4ad6da34fc02` | `3qEON3iXjNM` | 106440 | 138280 | 106s–138s | `krishnaji` | [Listen](https://www.youtube.com/watch?v=3qEON3iXjNM&t=106s) | `PASS` | `FAIL_BOUNDARY` | no need of this, because this had happened before so its not needed |
| 31 | `18fa8b66-496c-5486-8578-a68e205b7700` | `FoTH9BWP2gg` | 0 | 16000 | 0s–16s | `preethaji` | [Listen](https://www.youtube.com/watch?v=FoTH9BWP2gg&t=0s) | `PASS` | `UNSURE` | preethaji is asking for self reflection and this is not complete |
| 32 | `1965be58-bc89-5760-8a59-19629d21b75d` | `qDSfb0DZ0PE` | 44740 | 59540 | 44s–59s | `krishnaji` | [Listen](https://www.youtube.com/watch?v=qDSfb0DZ0PE&t=44s) | `PASS` | `FAIL_BOUNDARY` | |
| 33 | `1b2be475-7332-5765-aa15-24c43fbc3bd5` | `sMgbjxyrgqw` | 818610 | 854530 | 818s–854s | `krishnaji` | [Listen](https://www.youtube.com/watch?v=sMgbjxyrgqw&t=818s) | `PASS` | `FAIL_BOUNDARY` | |
| 34 | `1b2e053b-b2ac-534a-a8b5-f95f1aff9b24` | `_GEMrEWCiXw` | 1065980 | 1107580 | 1065s–1107s | `krishnaji` | [Listen](https://www.youtube.com/watch?v=_GEMrEWCiXw&t=1065s) | `PASS` | `FAIL_BOUNDARY` | |
| 35 | `1c202e65-73b5-542f-b0ea-3938f9f8fcb3` | `sOv9ISMIRQ0` | 0 | 13120 | 0s–13s | `preethaji` | [Listen](https://www.youtube.com/watch?v=sOv9ISMIRQ0&t=0s) | `PASS` | `FAIL_BOUNDARY` | this is a manifest program which is not needed and also this is already happened |
| 36 | `1d6c2225-75b9-5d10-a94d-d54c9bf04db1` | `tl31QISheOc` | 31440 | 64720 | 31s–64s | `preethaji` | [Listen](https://www.youtube.com/watch?v=tl31QISheOc&t=31s) | `PASS` | `PASS` | |
| 37 | `1df20e3b-f73c-5ce4-90b1-e381ca5cec9f` | `x-mTRlE0TC4` | 385570 | 394130 | 385s–394s | `krishnaji` | [Listen](https://www.youtube.com/watch?v=x-mTRlE0TC4&t=385s) | `PASS` | `FAIL_BOUNDARY` | |
| 38 | `1f6aa5da-3f13-59c7-ab9b-cb6898d026c0` | `T3I8r_NU2Wk` | 324720 | 398260 | 324s–398s | `preethaji` | [Listen](https://www.youtube.com/watch?v=T3I8r_NU2Wk&t=324s) | `PASS` | `FAIL_BOUNDARY` | |
| 39 | `20252ce5-d9c7-517c-8828-7bded06c4fa4` | `tCWfCISvo5k` | 628943 | 1171820 | 628s–1171s | `krishnaji` | [Listen](https://www.youtube.com/watch?v=tCWfCISvo5k&t=628s) | `PASS` | `PASS` | this is a meditation based technique which krishnaji is leading, I feel this can be stored much better |
| 40 | `2050bdeb-36e7-5d7d-af61-9456623a78a0` | `txmjnRTgB4Y` | 11360 | 27120 | 11s–27s | `preethaji` | [Listen](https://www.youtube.com/watch?v=txmjnRTgB4Y&t=11s) | `PASS` | `FAIL_BOUNDARY` | this can be deleted since it had happened, otherwise if anyone is asking for physical health related we can ask users to check oneness yoga  |
| 41 | `21105d61-bff7-55e0-8d04-19554e84a9e7` | `XzS56RqIxeE` | 107930 | 157770 | 107s–157s | `preethaji` | [Listen](https://www.youtube.com/watch?v=XzS56RqIxeE&t=107s) | `PASS` | `FAIL_BOUNDARY` | |
| 42 | `21d66f20-3427-5f9a-a37a-3b0ce1352d25` | `zPsun8EkA2s` | 31840 | 43840 | 31s–43s | `preethaji` | [Listen](https://www.youtube.com/watch?v=zPsun8EkA2s&t=31s) | `PASS` | `FAIL_BOUNDARY` | |
| 43 | `21f25c45-c9a2-58f0-8014-f2afc17e1314` | `R5jh4Ss4fKA` | 4200 | 30360 | 4s–30s | `krishnaji` | [Listen](https://www.youtube.com/watch?v=R5jh4Ss4fKA&t=4s) | `PASS` | `PASS` | can be made better |
| 44 | `22acb17e-b7ef-5afc-aabd-f6e20fc198b8` | `2z5qxSr4EaI` | 151360 | 165680 | 151s–165s | `preethaji` | [Listen](https://www.youtube.com/watch?v=2z5qxSr4EaI&t=151s) | `PASS` | `PASS` | can be made better |
| 45 | `22c2c5c8-64a0-57b5-8029-06fbedb1627e` | `Tc8f9ZasRRM` | 160 | 25520 | 0s–25s | `krishnaji` | [Listen](https://www.youtube.com/watch?v=Tc8f9ZasRRM&t=0s) | `PASS` | `FAIL_BOUNDARY` | |
| 46 | `25445c94-ab76-56bd-913d-abf4e244bf54` | `8mmungGgDNw` | 415540 | 427620 | 415s–427s | `krishnaji` | [Listen](https://www.youtube.com/watch?v=8mmungGgDNw&t=415s) | `PASS` | `FAIL_BOUNDARY` | krishnaji giving an example of a person experience, i feel this can be added and make this storing much better |
| 47 | `25762e5d-5fb3-51ca-b30b-b9729e2393de` | `zGOKGrTNlk4` | 42880 | 49200 | 42s–49s | `preethaji` | [Listen](https://www.youtube.com/watch?v=zGOKGrTNlk4&t=42s) | `PASS` | `FAIL_BOUNDARY` | |
| 48 | `27fba9bf-41c1-55f4-b9a1-f1b046b57d5b` | `Ao8Rhhl9E8k` | 82950 | 110210 | 82s–110s | `preethaji` | [Listen](https://www.youtube.com/watch?v=Ao8Rhhl9E8k&t=82s) | `PASS` | `FAIL_BOUNDARY` | |
| 49 | `295a5e1e-9f7e-587c-88d6-cdd8d0a948ac` | `Lm-5gKTKD7Y` | 384490 | 406730 | 384s–406s | `krishnaji` | [Listen](https://www.youtube.com/watch?v=Lm-5gKTKD7Y&t=384s) | `FAIL_SPEAKER` | `UNSURE` | this an experience shared by a devotee |
| 50 | `2c856f1e-f317-5a6e-a145-6348769b8c69` | `Y7p7jHP0Ii0` | 256170 | 384030 | 256s–384s | `krishnaji` | [Listen](https://www.youtube.com/watch?v=Y7p7jHP0Ii0&t=256s) | `PASS` | `FAIL_BOUNDARY` | |
