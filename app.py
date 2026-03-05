
from flask import Flask, request, jsonify
import json
import binascii
import asyncio
import itertools
import aiohttp
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from google.protobuf.json_format import MessageToJson
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import uid_generator_pb2
import like_count_pb2

app = Flask(__name__)

MAX_VISITS = 10000   # ULTRA POWERFUL LIMIT


def load_tokens(region):
    try:
        if region == "IND":
            with open("token_ind.json") as f:
                return json.load(f)
        elif region in {"BR","US","SAC","NA"}:
            with open("token_br.json") as f:
                return json.load(f)
        else:
            with open("token_bd.json") as f:
                return json.load(f)
    except:
        return []


def encrypt_message(plaintext):
    key = b'Yg&tc%DEuh6%Zc^8'
    iv = b'6oyZDr22E3ychjM%'
    cipher = AES.new(key, AES.MODE_CBC, iv)
    padded_message = pad(plaintext, AES.block_size)
    encrypted_message = cipher.encrypt(padded_message)
    return binascii.hexlify(encrypted_message).decode()


def create_protobuf(uid):
    message = uid_generator_pb2.uid_generator()
    message.saturn_ = int(uid)
    message.garena = 1
    return message.SerializeToString()


def enc(uid):
    protobuf_data = create_protobuf(uid)
    return encrypt_message(protobuf_data)


async def make_request_async(encrypt, region, token, session):
    try:
        if region == "IND":
            url = "https://client.ind.freefiremobile.com/GetPlayerPersonalShow"
        elif region in {"BR","US","SAC","NA"}:
            url = "https://client.us.freefiremobile.com/GetPlayerPersonalShow"
        else:
            url = "https://clientbp.ggblueshark.com/GetPlayerPersonalShow"

        headers = {
            "User-Agent": "Dalvik/2.1.0 (Linux; Android 9)",
            "Connection": "Keep-Alive",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Unity-Version": "2018.4.11f1",
            "ReleaseVersion": "OB52"
        }

        edata = bytes.fromhex(encrypt)

        async with session.post(url, data=edata, headers=headers, ssl=False, timeout=5) as response:
            if response.status != 200:
                return None

            hex_data = await response.read()
            binary = bytes.fromhex(hex_data.hex())
            items = like_count_pb2.Info()
            items.ParseFromString(binary)
            return items

    except:
        return None


@app.route("/visit")
async def visit():
    target_uid = request.args.get("uid")
    region = request.args.get("region","").upper()

    if not target_uid or not region:
        return jsonify({"error":"uid and region required"}),400

    tokens = load_tokens(region)

    if not tokens:
        return jsonify({"error":"no tokens loaded"}),500

    encrypted_uid = enc(target_uid)

    expanded_tokens = list(itertools.islice(itertools.cycle(tokens), MAX_VISITS))

    success = 0
    fail = 0
    player_name = None
    player_uid = None

    connector = aiohttp.TCPConnector(limit=2000)

    async with aiohttp.ClientSession(connector=connector) as session:

        tasks = [
            make_request_async(encrypted_uid, region, t["token"], session)
            for t in expanded_tokens
        ]

        results = await asyncio.gather(*tasks)

    for r in results:
        if r:
            success += 1
            if player_name is None:
                js = MessageToJson(r)
                data = json.loads(js)
                player_name = data.get("AccountInfo",{}).get("PlayerNickname","")
                player_uid = data.get("AccountInfo",{}).get("UID","")
        else:
            fail += 1

    return jsonify({
        "RequestedVisits": MAX_VISITS,
        "SuccessfulVisits": success,
        "FailedVisits": fail,
        "PlayerNickname": player_name,
        "UID": player_uid
    })


# OPTIONAL TOKEN REFRESH ENDPOINT
import httpx

LOGIN_API = "https://loginbp.ggblueshark.com/MajorLogin"

@app.route("/refresh")
async def refresh():

    try:
        with open("accounts.json") as f:
            accounts = json.load(f)
    except:
        return {"error":"accounts.json missing"}

    tokens = []

    async with httpx.AsyncClient() as client:

        tasks = [
            client.post(LOGIN_API, json=acc, timeout=10)
            for acc in accounts
        ]

        responses = await asyncio.gather(*tasks, return_exceptions=True)

    for r in responses:
        try:
            data = r.json()
            token = data.get("token")
            if token:
                tokens.append({"token": token})
        except:
            pass

    with open("token_ind.json","w") as f:
        json.dump(tokens,f,indent=2)

    return {
        "status":"tokens refreshed",
        "total_tokens": len(tokens)
    }
