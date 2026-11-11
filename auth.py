import aiohttp
import ssl
import random
import uuid
from datetime import datetime
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from encrypt import HELLXenc_packet
from proto import HELLXcreate_proto, HELLXgenerate_packet, HELLXgenerate_packet_plain, HELLXenc_varint
from Pb2 import MajoRLoGinrEs_pb2, PorTs_pb2


async def HELLXfetch_version():
    # Ghost-style version + server_url
    url = (
        "https://version.ggwhitehawk.com/live/ver.php"
        "?version=1.132.17&lang=en&device=android&channel=android"
        "&appstore=googleplay&region=ME"
        "&whitelist_version=1.3.0&whitelist_sp_version=1.0.0"
    )
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=12) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    ver = data.get("remote_version") or data.get("client_version") or "1.132.17"
                    server_url = data.get("server_url") or ""
                    if server_url and not server_url.startswith("http"):
                        server_url = "https://" + server_url
                    if server_url and not server_url.endswith("/"):
                        server_url = server_url + "/"
                    release = data.get("latest_release_version") or "OB55"
                    client_ip = data.get("client_ip") or data.get("ip") or ""
                    return ver, server_url, client_ip, release
    except Exception as e:
        print("HELLX => [VERSION]: %s" % e)
    return "1.132.17", "https://loginbp.ppmainecoonghj.com/", "", "OB55"


async def HELLXfetch_city(ip):
    # optional geo; never block login
    return "Jakarta"


async def HELLXgenerate_access(uid, password, user_agent):
    url = "https://100067.connect.garena.com/oauth/guest/token/grant"
    data = {
        "uid": uid,
        "password": password,
        "response_type": "token",
        "client_type": "2",
        "client_secret": "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3",
        "client_id": "100067"
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers={
            "Host": "100067.connect.garena.com",
            "User-Agent": user_agent,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "close"
        }, data=data) as response:
            if response.status != 200:
                return None, None
            res_data = await response.json()
            return res_data.get("open_id"), res_data.get("access_token")
def _pb_varint(n):
    out = []
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            break
    return bytes(out)


def _pb_field(fn, val):
    if isinstance(val, int):
        return _pb_varint((fn << 3) | 0) + _pb_varint(val)
    if isinstance(val, str):
        d = val.encode()
    elif isinstance(val, bytes):
        d = val
    else:
        return b""
    return _pb_varint((fn << 3) | 2) + _pb_varint(len(d)) + d


def HELLXbuild_major_login(open_id, access_token, version, client_ip, city):
    try:
        from Pb2 import MajoRLoGinrEq_pb2 as ML
        proto = ML.MajorLogin()
        proto.event_time = str(datetime.now())[:-7]
        proto.game_name = "free fire"
        proto.platform_id = 1
        proto.client_version = str(version or "1.132.17")
        proto.client_version_code = "2019121229"
        proto.system_software = "Android OS 15 / API-35 (AP3A.240905.015.A2/185014)"
        proto.system_hardware = "Handheld"
        proto.device_type = "Handheld"
        proto.screen_width = 1600
        proto.screen_height = 719
        proto.screen_dpi = "234"
        proto.processor_details = "ARM64 FP ASIMD AES | 1820 | 8"
        proto.memory = 2798
        proto.gpu_renderer = "Mali-G57"
        proto.gpu_version = "OpenGL ES 3.2 v1.r49p1-04eac0.2848c17a2fd4e9340e06555168eaa3c9"
        proto.unique_device_id = "Google|" + str(uuid.uuid4())
        # use random IP like Ghost, not the version-api IP (that can trigger abnormal client)
        proto.client_ip = "%d.%d.%d.%d" % (
            random.randint(103, 223),
            random.randint(10, 250),
            random.randint(10, 250),
            random.randint(10, 250),
        )
        proto.language = "hi"
        proto.open_id = str(open_id)
        proto.open_id_type = "4"
        proto.login_open_id_type = 4
        proto.access_token = str(access_token)
        proto.login_by = 2
        proto.platform_sdk_id = 1
        proto.origin_platform_type = "4"
        proto.primary_platform_type = "4"
        proto.reg_avatar = 1
        proto.channel_type = 3
        proto.telecom_operator = "JIO"
        proto.network_operator_a = "JIO"
        proto.network_type = "WIFI"
        proto.network_type_a = "WIFI"
        proto.cpu_type = 2
        proto.cpu_architecture = "64"
        proto.graphics_api = "OpenGLES2"
        proto.supported_astc_bitset = 8191
        proto.client_using_version = "7428b253defc164018c604a1ebbfebdf"
        proto.loading_time = 15078
        proto.release_channel = "android"
        proto.extra_info = "KqsHTx3+QOmBRR1WKvaWewlcpqJBfjki+PPHQoQG8+0yV+Uos7gUFFjHMQ/e7u6han6Fl77r7c3vMN3p8UbKgN+nfycQCgwBmWgBzomx2gj84c+p"
        proto.android_engine_init_flag = 111207
        proto.if_push = 1
        proto.is_vpn = 0
        try:
            proto.memory_available.version = 55
            proto.memory_available.hidden_value = 81
        except Exception:
            pass
        proto.external_storage_total = 49973
        proto.external_storage_available = 11338
        proto.internal_storage_total = 854
        proto.internal_storage_available = 11466
        proto.game_disk_storage_total = 49973
        proto.game_disk_storage_available = 11466
        proto.external_sdcard_total_storage = 49973
        proto.external_sdcard_avail_storage = 11466
        proto.library_path = "/data/app/~~lHFxTCCbupG2QVJmsURtZw==/com.dts.freefireth-N3aCHpHNXpdxjD80uIIbww==/lib/arm64"
        proto.library_token = "b8e0cd5e295eee42f5860d3c86e483dd|/data/app/~~lHFxTCCbupG2QVJmsURtZw==/com.dts.freefireth-N3aCHpHNXpdxjD80uIIbww==/base.apk"
        base_payload = proto.SerializeToString()
        extra = b""
        extra += _pb_field(96, '{"cur_rate":[90,60,120],"support_etc2":false}')
        extra += _pb_field(97, 1)
        extra += _pb_field(99, "4")
        extra += _pb_field(100, "4")
        extra += _pb_field(102, b"\x17]ENWU\x0eR5")
        extra += _pb_field(104, 52882)
        extra += _pb_field(105, 1)
        extra += _pb_field(106, "https://dl.ak.freefiremobile.com/live/ABHotUpdates/|https://core-ak.freefiremobile.com/live/ABHotUpdates/|6b2078db9d22dd98f8e9386a39af8462")
        extra += _pb_field(107, "c8e41b7a93f02d56e1a94c7b8203f5d1")
        key = b"Yg&tc%DEuh6%Zc^8"
        iv = b"6oyZDr22E3ychjM%"
        cipher = AES.new(key, AES.MODE_CBC, iv)
        return cipher.encrypt(pad(base_payload + extra, AES.block_size))
    except Exception as e:
        print("HELLX => [MAJOR BUILD]: %s" % e)
        return None


def HELLXbuild_get_login_data_payload(open_id, access_token, version="1.132.17", client_ip="129.45.8.219", city="Oran"):
    fields = {
        3: datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        4: "free fire",
        5: 1,
        7: version or "1.132.17",
        8: "Android OS 14 / API-34 (UP1A.231005.007/A136BXXU1AXA1)",
        9: "Handheld",
        10: "Telkomsel",
        11: "CarrierDataNetwork",
        12: 1639,
        13: 720,
        14: "320",
        15: "ARM64 FP ASIMD AES | 2000 | 8",
        16: 5653,
        17: "Mali-G52 MC2",
        18: "OpenGL ES 3.2 v1.r49p1-03bet0",
        19: f"Google|{uuid.uuid4()}",
        20: client_ip if client_ip else "%d.%d.%d.%d" % (random.randint(103,223), random.randint(10,250), random.randint(10,250), random.randint(10,250)),
        21: "en",
        22: str(open_id),
        23: "4",
        24: "Handheld",
        25: "Xiaomi",
        26: "ID",
        29: str(access_token),
        30: 1,
        41: "Telkomsel",
        42: "4G",
        57: "7428b253defc164018c604a1ebbfebdf",
        60: 109278,
        61: 55402,
        62: 868,
        64: 55927,
        65: 109278,
        66: 55927,
        67: 109278,
        73: 2,
        74: "/data/app/~~6Cw028g_ld-8Z0z2qhrOLA==/com.dts.freefireth-i3wiaEmpx8CbiRVhUMx_ag==/lib/arm64",
        76: 1,
        77: "b8e0cd5e295eee42f5860d3c86e483dd|/data/app/~~6Cw028g_ld-8Z0z2qhrOLA==/com.dts.freefireth-i3wiaEmpx8CbiRVhUMx_ag==/base.apk",
        78: 6,
        79: 1,
        81: "32",
        83: "2019121229",
        85: 3,
        86: "OpenGLES2",
        87: 3071,
        88: 4,
        89: 14466,
        93: "3rd_party",
        94: "KqsHTyb7yHjsAiyNWUUZa0DSOD6U0AhDQ76smAo1WeHHHpSmJ8KMRyRrxb2ttgJqO9YOqO/K6AORAvDMAX/qBS8+JahIkrM7kHfzlfULbgRAoZ9r",
        95: "111207",
        96: "{\"cur_rate\":[60,90,120],\"support_etc2\":true}",
        97: "1",
        98: "1",
        99: "4",
        100: "4",
        103: "1",
        104: "52837",
        105: "1",
    }
    proto_bytes = HELLXcreate_proto(fields)
    key = b'Yg&tc%DEuh6%Zc^8'
    iv = b'6oyZDr22E3ychjM%'
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return cipher.encrypt(pad(proto_bytes, AES.block_size))


async def HELLXmajor_login(payload, headers, server_url="https://loginbp.ppmainecoonghj.com/", release="OB55"):
    if not payload:
        print("HELLX => [MAJORLOGIN]: empty payload")
        return None
    servers = []
    if server_url:
        s = server_url if server_url.startswith("http") else "https://" + server_url
        if not s.endswith("/"):
            s += "/"
        servers.append(s)
    for extra in (
        "https://loginbp.ppmainecoonghj.com/",
    ):
        if extra not in servers:
            servers.append(extra)
    req_headers = dict(headers)
    req_headers["ReleaseVersion"] = str(release or "OB55")
    req_headers["User-Agent"] = "UnityPlayer/2018.4.12f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)"
    req_headers["X-Unity-Version"] = "2018.4.12f1"
    req_headers["Content-Type"] = "application/x-www-form-urlencoded"
    req_headers["Accept-Encoding"] = "identity"
    req_headers["Connection"] = "Keep-Alive"
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    last_err = None
    async with aiohttp.ClientSession() as session:
        for base in servers:
            url = base.rstrip("/") + "/MajorLogin"
            try:
                from urllib.parse import urlparse
                h = dict(req_headers)
                h["Host"] = urlparse(url).netloc
                async with session.post(url, data=payload, headers=h, ssl=ssl_context, timeout=20) as response:
                    body = await response.read()
                    if response.status != 200:
                        last_err = "HTTP %s %r" % (response.status, body[:80])
                        continue
                    if len(body) < 40:
                        last_err = "short body %d" % len(body)
                        continue
                    # reject plain-text error responses
                    if body.startswith(b"BR_") or body.startswith(b"{"):
                        last_err = "server error %r" % body[:80]
                        continue
                    return body
            except Exception as e:
                last_err = str(e)
                continue
    if last_err:
        print("HELLX => [MAJORLOGIN]: %s" % last_err)
    return None



async def HELLXget_login_data(base_url, open_id, access_token, token, headers, version="1.132.17", client_ip="129.45.8.219", city="Oran", payload=None, release="OB55"):
    """GetLoginData — MUST reuse MajorLogin encrypted payload when possible.
    Sending a different device fingerprint than MajorLogin is a known guest-ban trigger.
    """
    tok = (token.decode("utf-8", errors="ignore") if isinstance(token, (bytes, bytearray)) else str(token or "")).strip()
    if not tok:
        print("HELLX => [AUTH]: GetLoginData SKIP — empty token")
        return None

    bu = (base_url or "").strip() if isinstance(base_url, str) else ""
    if not bu.startswith("http://") and not bu.startswith("https://"):
        bu = "https://clientbp.ppmainecoonghj.com"
    bu = bu.rstrip("/")
    url = f"{bu}/GetLoginData"

    # Critical: reuse MajorLogin payload if provided (same device session)
    if payload is None:
        payload = HELLXbuild_get_login_data_payload(open_id, access_token, version, client_ip, city)
    if not payload:
        print("HELLX => [AUTH]: GetLoginData FAILED — empty payload")
        return None

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    current_headers = dict(headers) if headers else {}
    current_headers["Authorization"] = f"Bearer {tok}"
    current_headers["ReleaseVersion"] = str(release or "OB55")
    current_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    current_headers.setdefault("Accept-Encoding", "gzip")
    current_headers.setdefault("Connection", "Keep-Alive")
    current_headers.setdefault("User-Agent", "UnityPlayer/2018.4.12f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)")
    current_headers.setdefault("X-Unity-Version", "2018.4.12f1")
    try:
        from urllib.parse import urlparse
        host = urlparse(bu).hostname
        current_headers["Host"] = host or "clientbp.ppmainecoonghj.com"
    except Exception:
        current_headers["Host"] = "clientbp.ppmainecoonghj.com"

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, data=payload, headers=current_headers, ssl=ssl_context, timeout=30) as response:
                if response.status == 200:
                    body = await response.read()
                    if body and not body.startswith(b"BR_") and not body.startswith(b"{"):
                        return body
                    print(f"HELLX => [AUTH]: GetLoginData bad body from {url}: {body[:80]!r}")
                    return None
                print(f"HELLX => [AUTH]: GetLoginData HTTP {response.status} from {url}")
                return None
        except Exception as e:
            print(f"HELLX => [AUTH]: GetLoginData Exception: {e}")
            return None
def HELLXdecode_major_login(response_bytes):
    data = response_bytes or b""
    # try raw + AES-decrypted variants
    candidates = [data]
    try:
        key = b"Yg&tc%DEuh6%Zc^8"
        iv = b"6oyZDr22E3ychjM%"
        if len(data) >= 16 and len(data) % 16 == 0:
            from Crypto.Util.Padding import unpad
            dec = AES.new(key, AES.MODE_CBC, iv).decrypt(data)
            try:
                candidates.append(unpad(dec, 16))
            except Exception:
                candidates.append(dec)
    except Exception:
        pass
    best = None
    for blob in candidates:
        for off in range(0, min(160, len(blob))):
            try:
                c = MajoRLoGinrEs_pb2.MajorLoginRes()
                c.ParseFromString(blob[off:])
                if c.account_uid and c.token:
                    return c
                if c.token and best is None:
                    best = c
            except Exception:
                continue
    if best is not None:
        return best
    proto = MajoRLoGinrEs_pb2.MajorLoginRes()
    try:
        proto.ParseFromString(data)
    except Exception:
        pass
    return proto



def HELLXdecode_login_data(response_bytes):
    proto = PorTs_pb2.GetLoginData()
    proto.ParseFromString(response_bytes)
    return proto
def HELLXbuild_fnl_token_ghost(account_uid, token, kts, key, iv):
    """Ghost xGetFNLToKeN — Online final token (830c)."""
    if isinstance(token, bytes):
        token_bytes = token
    else:
        token_bytes = str(token or "").encode("utf-8")
    cipher = AES.new(key, AES.MODE_CBC, iv)
    enc_token = cipher.encrypt(pad(token_bytes, 16))
    return (
        bytes.fromhex("830c")
        + int(account_uid).to_bytes(8, "big")
        + int(kts).to_bytes(4, "big")
        + len(enc_token).to_bytes(8, "big")
        + enc_token
    )


def HELLXbuild_chat_auth_token(account_id, jwt_token, timestamp, key, iv):
    """Ghost CrAuThTK — Chat auth (6d19)."""
    if isinstance(jwt_token, bytes):
        jwt_token = jwt_token.decode("utf-8", errors="ignore")
    jwt_token = str(jwt_token or "")
    K = key if isinstance(key, (bytes, bytearray)) else bytes.fromhex(str(key))
    V = iv if isinstance(iv, (bytes, bytearray)) else bytes.fromhex(str(iv))
    ct = AES.new(K, AES.MODE_CBC, V).encrypt(pad(jwt_token.encode("utf-8"), AES.block_size))
    return (
        bytes.fromhex("6d19")
        + int(account_id).to_bytes(8, "big")
        + int(timestamp).to_bytes(4, "big")
        + len(ct).to_bytes(4, "big")
        + ct
    )


def HELLXbuild_final_token(account_id, token, server_time, key, iv, typ="OnLine"):
    """Guild ZIX final token as hex. Pads length field so total hex is always even."""
    if isinstance(token, bytes):
        token = token.decode("utf-8", errors="ignore")
    token = str(token or "")
    uid_hex = "%016x" % int(account_id)
    ts_hex = "%08x" % int(server_time)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    enc = cipher.encrypt(pad(token.encode("utf-8"), AES.block_size)).hex()
    enc_len = "%x" % (len(enc) // 2)
    if typ == "OnLine":
        # 8215 + uid16 + ts8 + pad + len + enc  must be even length
        core = "8215%s%s" % (uid_hex, ts_hex)
        # fixed 8-hex-digit length field
        body = core + ("%08x" % (len(enc) // 2)) + enc
    else:
        core = "8415%s%s" % (uid_hex, ts_hex)
        body = core + ("%08x" % (len(enc) // 2)) + enc
    if len(body) % 2:
        body = body + "0"
    return body


def HELLXbuild_final_token_bytes(account_id, token, server_time, key, iv, typ="OnLine"):
    return bytes.fromhex(HELLXbuild_final_token(account_id, token, server_time, key, iv, typ))


def HELLXbuild_auth_startup(uid, token, timestamp, key, iv):
    # Prefer Ghost binary final token (reliable). Returned as hex for connect_online.
    return HELLXbuild_fnl_token_ghost(uid, token, timestamp, key, iv).hex()


_PKT2_INNER_BLOB = bytes.fromhex(
    '6db490eb03aadf4f1901d5762b2a15959a10cd867a845c4105a27aed4faad29b'
    '6889119641a5e0ec13d3a25855acfc12635979c40be6d74ab1c3023b9c664eaf'
    '3e4d75d02cf7233a056713efa599142bffa45cb0e1a3b8099ec0cd50ce3a5544'
    '69559bf663164e1a3577aa6e3f019a7103ef6d153ef39d18525499628c76cf5a'
    '0cdb0ea3001a6080bd5caf27684934e656eec792ca6096a57e9f0091ed07b78b'
    '2f2dc58993c2fdad15bf0b001c26d8dfd28cd217407d7e04bac5651d75cfeb60'
    '94213583a836566fa7425881bdfd915f25c00e469de2ffcaf975d799547101bd'
    'a95b4a9b38bb5555e37cce84fc515596f03f6f513b4e6332b4283fc68543fe35'
    '96272093a1bf4989438a99272b482addabd7910dad1031efa836d3bfdfb26cb6'
    'd9a718fb7852820722507692393161f747d74e1e95874911f3334f9e5ac6bd17'
    '998d094696e736db326314b4301644717e22a280a0aa33b5a07e7609e127b9ad'
    '803afa3291407088d76e35eac163f951a0fc1349d3db022e63b0670fea37585c'
    '15151c4f032174cbcf01ffc9656d14846123ab1c37df3b4960c3c37234bb7d97'
    '0ec8085337e1c7f6dc3aa7761352c9257f7a00461a4cac9840918308084851e0'
    '0160a84494b2f1067711725f4b711f3140578e826a28ce142abe11871b9064a3'
    'eecffe4bae380a66bed4d20ec6'
)

def HELLXbuild_post_auth_packets(uid, jwt_token, key, iv):
    uid_hex = hex(int(uid))[2:]
    if len(uid_hex) % 2:
        uid_hex = "0" + uid_hex
    if len(uid_hex) < 8:
        uid_hex = uid_hex.zfill(8)
    uid_pad = uid_hex
    if not jwt_token:
        return ()
    if isinstance(jwt_token, bytes):
        jwt_bytes = jwt_token
    else:
        jwt_bytes = str(jwt_token).encode()
    cipher1 = AES.new(key, AES.MODE_CBC, iv)
    enc_jwt = cipher1.encrypt(pad(jwt_bytes, AES.block_size))
    enc_len_hex = hex(len(enc_jwt))[2:].zfill(8)
    pkt1 = bytes.fromhex('830c' + enc_len_hex + uid_pad) + enc_jwt

    inner = _PKT2_INNER_BLOB
    inner_len_varint = HELLXenc_varint(len(inner))
    field1_tag = b'\x0a'
    inner_wrapped = field1_tag + inner_len_varint + inner
    field2_content = HELLXenc_varint(2) + HELLXenc_varint(len(inner_wrapped)) + inner_wrapped
    pkt2_proto = b'\x08\x02\x12' + HELLXenc_varint(len(inner_wrapped)) + inner_wrapped
    cipher2 = AES.new(key, AES.MODE_CBC, iv)
    enc2 = cipher2.encrypt(pad(pkt2_proto, AES.block_size))
    enc2_len_hex = hex(len(enc2))[2:].zfill(8)
    pkt2 = bytes.fromhex('280c' + enc2_len_hex) + enc2

    fields_pkt3 = {1: 6, 2: {1: 3, 2: "2019120816", 3: 1}}
    proto3 = HELLXcreate_proto(fields_pkt3)
    cipher3 = AES.new(key, AES.MODE_CBC, iv)
    enc3 = cipher3.encrypt(pad(proto3, AES.block_size))
    enc3_len_hex = hex(len(enc3))[2:].zfill(8)
    pkt3 = bytes.fromhex('1d0c' + enc3_len_hex) + enc3

    fields_pkt4 = {1: 7, 2: b''}
    proto4 = HELLXcreate_proto(fields_pkt4)
    cipher4 = AES.new(key, AES.MODE_CBC, iv)
    enc4 = cipher4.encrypt(pad(proto4, AES.block_size))
    enc4_len_hex = hex(len(enc4))[2:].zfill(8)
    pkt4 = bytes.fromhex('280c' + enc4_len_hex) + enc4

    return pkt1, pkt2, pkt3, pkt4
def HELLXbuild_ping_packet(key, iv):
    fields = {
        1: 15,
        2: {
            1: 804266360,
            2: 1
        }
    }
    proto_hex = HELLXcreate_proto(fields).hex()
    return HELLXgenerate_packet(proto_hex, '0515', key, iv)
def HELLXbuild_accept_invite(owner_uid, code, key, iv):
    fields = {
        1: 4,
        2: {
            1: int(owner_uid),
            3: int(owner_uid),
            4: bytes.fromhex("01030407090a0b1216191a201d27"),
            8: 1,
            9: {
                1: "088ED288AA30EE9402010100000000120013000100000001B8B110CD0F0000004676251400000000000000000000000000000000000000ff00000000cacfa16d",
                2: 53,
                4: "~[YP",
                6: 11,
                8: "1.132.17",
                9: 6,
                10: 2
            },
            10: str(code),
            11: [
                {1: "IDC1", 2: 68, 3: "EUROPE"},
                {1: "IDC2", 2: 25, 3: "EUROPE"},
            ],
            13: "tr",
            16: bytes.fromhex("374f5219"),
            20: [
                {1: 3, 2: 357},
                {1: 4, 2: 385},
                {1: 5, 2: 156},
                {1: 29, 2: 204},
                {1: 22, 2: 115},
                {1: 14, 2: 139},
                {1: 21},
            ],
        }
    }
    proto_hex = HELLXcreate_proto(fields).hex()
    return HELLXgenerate_packet(proto_hex, '0515', key, iv)
def HELLXbuild_join_sq(uid: int, code: str, key: bytes, iv: bytes) -> bytes:
    nested_fields = {
        1: bytes.fromhex("01090a0b121619201d2729"),
        2: 40,
        3: bytes.fromhex("01090a0b121619201d2729"),
        4: "w\\Z]",
        6: 12,
        7: bytes.fromhex("01090a0b121619201d2729"),
        8: "1.132.17",
        9: 6,
        10: 2,
        11: bytes.fromhex("01090a0b121619201d2729"),
    }
    fields = {
        1: 4,
        2: {
            4: bytes.fromhex("01090a0b121619201d2729"),
            5: str(code),
            6: 6,
            8: 1,
            9: nested_fields,
            11: {1: "IDC1", 2: 99, 3: "ME"},
            13: "ar",
            16: bytes.fromhex("374f521955"),
            20: [
                {1: 3, 2: 360},
                {1: 4, 2: 391},
                {1: 5, 2: 156},
                {1: 29, 2: 204},
                {1: 22, 2: 118},
                {1: 14, 2: 139},
                {1: 21},
            ],
            27: {1: 2, 2: 4},
        },
    }
    proto_hex = HELLXcreate_proto(fields).hex()
    return HELLXgenerate_packet(proto_hex, "0519", key, iv)

import struct as _struct
_VOICE_BASE_HEX = (
    '0a8e01'
    '0811100b180122'
    '04534f4e59'
    '2a013930cc80868c02'
    '3a0b61726d65616269'
    '2d763761'
    '4200'
    '4a2438323934386166322d313737392d346438372d613864352d356237363962376365623934'
    '522a464644353846423446373646363438433241354532314542434641334141453831423443394237443937'
    '5a05766f696365'
    '62075851'
    '2d42453432'
    '6802'
    '720471636f6d'
    '100b'
)
_STEP1_FIXED128_HEX = (
    '69839458c071310bbc7e2eede4101c55f0e8c682102c5b100c79'
    '291ae9800ad21d16f7a4e484d4c09f5960f58d00a576128a7bad'
    '036fe886b369e6e2e07ad339be2d93f40eb37e640790972809ea'
    '078b24540912ca6dd3f54183ac721db4c50cd3703941'
    '9f467a430d9429eeee04ead8b83073e54e45a51e0d33b9b273fd2942'
)
def _make_voice_packet(pkt_type: int, region_id: int, uid: str) -> bytes:
    RAW = bytearray(bytes.fromhex(_VOICE_BASE_HEX))
    RAW[4] = pkt_type
    return _struct.pack('>I', len(RAW)) + bytes(RAW)
def HELLXbuild_voice_step1(uid: str, region_id: int) -> bytes:
    base = bytearray(bytes.fromhex(_VOICE_BASE_HEX))
    base[4] = 0x00
    fixed128 = bytes.fromhex(_STEP1_FIXED128_HEX)
    payload = bytes(base) + b'\x12\x80\x01' + fixed128 + b'\x18\x01\x20\x06\x38\x01'
    return _struct.pack('>I', len(payload)) + payload
def HELLXbuild_voice_auth(uid: str, region_id: int, voice_port: int, region_prefix: str = "EUROPE") -> bytes:
    base = bytearray(bytes.fromhex(_VOICE_BASE_HEX))
    base[4] = 0x07
    device_id = "FFD58FB4F76F648C2A5E21EBCFA3AAE81B4C9B7D97"
    region_str = f"{region_prefix}_{region_id}"
    field2_str = (device_id + region_str).encode()
    uid_b = uid.encode()
    field2_len = len(field2_str)
    field2_len_varint = bytes([field2_len]) if field2_len < 128 else bytes([0x80 | (field2_len & 0x7F), field2_len >> 7])
    payload = (
        bytes(base) +
        b'\x12' + field2_len_varint + field2_str +
        bytes.fromhex('20052801' '30d008' '380040005001') +
        b'\x5a' + bytes([len(uid_b)]) + uid_b +
        bytes.fromhex('60007000800101')
    )
    return _struct.pack('>I', len(payload)) + payload
def HELLXbuild_voice_ping(uid: str, region_id: int, voice_port: int, session_id: int = 0x0b) -> bytes:
    base = bytearray(bytes.fromhex(_VOICE_BASE_HEX))
    base[4] = 0x09
    base_bytes = bytes(base[:-2])
    session_varint = HELLXenc_varint(session_id)
    payload = base_bytes + b'\x10' + session_varint
    return _struct.pack('>I', len(payload)) + payload
def HELLXbuild_voice_stat_report(uid: str, region_id: int, session_id: int, region_prefix: str = "EUROPE") -> bytes:
    base = bytearray(bytes.fromhex(_VOICE_BASE_HEX))
    base[4] = 0x38
    base_bytes = bytes(base[:-2])
    region_str = f"{region_prefix}_{region_id}".encode()
    session_varint = HELLXenc_varint(session_id)
    payload = (
        base_bytes +
        b'\x10' + session_varint +
        b'\x1a\x40' + b'FFD58FB4F76F648C2A5E21EBCFA3AAE81B4C9B7D97'.encode() +
        region_str
    )
    return _struct.pack('>I', len(payload)) + payload
def HELLXbuild_voice_broadcast_sub(uid: str, region_id: int, session_id: int, region_prefix: str = "EUROPE") -> bytes:
    base = bytearray(bytes.fromhex(_VOICE_BASE_HEX))
    base[4] = 0x37
    base_bytes = bytes(base[:-2])
    region_str = f"{region_prefix}_{region_id}".encode()
    session_varint = HELLXenc_varint(session_id)
    payload = (
        base_bytes +
        b'\x10' + session_varint +
        b'\x1a\x40' + b'FFD58FB4F76F648C2A5E21EBCFA3AAE81B4C9B7D97'.encode() +
        region_str +
        b'\x22\x03all'
    )
    return _struct.pack('>I', len(payload)) + payload
def HELLXbuild_voice_join(uid: str, region_id: int, counter: int, voice_secret: str, chat_key: str, region_prefix: str = "EUROPE") -> bytes:
    base = bytearray(bytes.fromhex(_VOICE_BASE_HEX))
    base[4] = 0x18
    device_id = "FFD58FB4F76F648C2A5E21EBCFA3AAE81B4C9B7D97"
    region_str = f"{region_prefix}_{region_id}"
    field2_str = (device_id + region_str).encode()
    uid_b = uid.encode()
    uid_last3 = uid.zfill(11)[-3:].encode()
    field2_len = len(field2_str)
    field2_len_varint = bytes([field2_len]) if field2_len < 128 else bytes([0x80 | (field2_len & 0x7F), field2_len >> 7])
    flag = b'\x01' if counter == 0 else b'\x00'
    payload = (
        bytes(base) +
        b'\x12' + field2_len_varint + field2_str +
        bytes.fromhex('20052801' '30d008' '380040005001') +
        b'\x5a' + bytes([len(uid_b)]) + uid_b +
        bytes.fromhex('60007000800101') +
        b'\x1a\x0b' + uid_last3 +
        bytes([0x20, counter & 0xFF, 0x28]) + flag
    )
    return _struct.pack('>I', len(payload)) + payload
def HELLXbuild_voice_auth_device(uid: str, region_id: int) -> bytes:
    payload = bytearray()
    payload.append(0x01)
    payload.append(0x0a)
    device_model = b"samsung"
    payload.append(len(device_model))
    payload.extend(device_model)
    payload.append(0x12)
    device_info = b"SM-S9210"
    payload.append(len(device_info))
    payload.extend(device_info)
    length = len(payload)
    return _struct.pack('>I', length) + bytes(payload)
import time as _time
_VOICE_CUSTOM_MAGIC = bytes.fromhex('feffffff04b50001')
def HELLXbuild_voice_custom(uid: str, region_id: int, uuid: str = "f687ba460e-9b6b8bc39",
                              device_id: str = "F76F648CCFA3AAE897",
                              mcu_ip: str = "0.0.0.0",
                              region_prefix: str = "EUROPE") -> bytes:
    uid_str = uid.zfill(11)
    uid_last3 = uid_str[-3:].encode()
    region_str = f"{region_prefix}_{region_id}".encode()
    uuid_b = uuid.encode()
    device_b = device_id.encode()
    local_ip = b"0.0.0.0"
    mcu_ip_b = mcu_ip.encode()
    ts = int(_time.time()) & 0xFFFFFFFF
    pkt = bytearray()
    pkt.extend(_VOICE_CUSTOM_MAGIC)
    pkt.extend(b'\x00\x24')
    pkt.extend(uuid_b); pkt.append(0)
    pkt.extend(b'\x00\x2a')
    pkt.extend(device_b); pkt.append(0)
    pkt.extend(b'\x00\x1a')
    pkt.extend(region_str); pkt.append(0)
    pkt.extend(b'\x00\x0b')
    pkt.extend(uid_last3); pkt.extend(b'\x00\x00\x00\x00')
    pkt.extend(b'\x28\x2e\x30\x00')
    pkt.append(0x07)
    pkt.extend(local_ip); pkt.extend(b'\x00')
    pkt.append(0x0d)
    pkt.extend(mcu_ip_b); pkt.extend(b'\x00')
    pkt.extend(b'\x17\x76')
    pkt.extend(_struct.pack('>I', ts))
    pkt.extend(b'\x00\x00\x00\x00')
    return _struct.pack('>I', len(pkt)) + bytes(pkt)
def HELLXparse_voice_custom_response(data: bytes):
    if len(data) > 4 and data[4:8] == b'\xfe\xff\xff\x7f':
        data = data[4:]
    if not data.startswith(b'\xfe\xff\xff\x7f'):
        return None
    import re
    matches = re.findall(rb'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', data)
    for m in matches:
        parts = m.split(b'.')
        if all(0 <= int(p) <= 255 for p in parts) and parts[0] not in (b'0', b'1'):
            return m.decode()
    return None
def HELLXbuild_chat_auth(uid: int, region_id, key, iv) -> bytes:
    # fields = {
    #     1: 3,
    #     2: {
    #         1: uid,
    #         3: "en",
    #         4: str(region_id),
    #     }
    # }
    fields = {1: 3, 2: {1: int(uid), 3: 'en', 4: str(region_id)}}
    print(fields)
    print("________________________________________________________________________________________________")
    proto_hex = HELLXcreate_proto(fields).hex()
    return HELLXgenerate_packet(proto_hex, '1215', key, iv)
def HELLXbuild_chat_global_auth(key, iv) -> bytes:
    fields = {
        1: 3,
        2: {
            2: 5,
            3: "en",
        }
    }
    proto_hex = HELLXcreate_proto(fields).hex()
    return HELLXgenerate_packet(proto_hex, '1215', key, iv)
async def get_randm_avatar():
    avatars = [902000068, 902000016, 902000011, 902000084, 902000085, 902000087, 902000106, 902045016]
    return random.choice(avatars)
async def HELLXbuild_chat_message(uid: int, owner_uid: int, message: str, timestamp: int, key, iv) -> bytes:
    fields = {
        1: 1,
        2: {
            1: uid,
            2: owner_uid,
            4: message,
            5: timestamp,
            7: 6,
            9: {
                1: "HELLX",
                2: await get_randm_avatar(),
                3: 901000029,
                4: 330,
                5: 801043518,
                7: 2,
                10: 1,
                12: 0,
                13: {
                    1: 2,
                },
                13: "",
                14: {
                    1: uid,
                    2: 8,
                    3: "\u0010\u0015\b\n\u000b\u0013\f\u000f\u0011\u0004\u0007\u0002\u0003\r\u000e\u0012\u0001\u0005\u0006",
                }
            },
            10: "en",
            13: {3: 1},
            14: "",
        }
    }
    print(fields)
    proto_hex = HELLXcreate_proto(fields).hex()
    return HELLXgenerate_packet(proto_hex, '1215', key, iv)
def HELLXbuild_leave_team(uid: int, key, iv) -> bytes:
    fields = {
        1: 7,
        2: {1: uid}
    }
    proto_hex = HELLXcreate_proto(fields).hex()
    return HELLXgenerate_packet(proto_hex, '0515', key, iv)
def HELLXbuild_chat_close(uid: int, key, iv) -> bytes:
    fields = {
        1: 4,
        2: {
            1: uid,
            3: "en",
        }
    }
    proto_hex = HELLXcreate_proto(fields).hex()
    return HELLXgenerate_packet(proto_hex, '1215', key, iv)
def HELLXbuild_voice_redirect(uid: str, region_id: int, region_prefix: str = "EUROPE", ext_region: str = "de") -> bytes:
    device_id = "FFD58FB4F76F648C2A5E21EBCFA3AAE81B4C9B7D97"
    region_str = f"{region_prefix}_{region_id}"
    field1 = (device_id + region_str).encode()
    base = bytes.fromhex(_VOICE_BASE_HEX)
    inner = bytearray(base[3:3+142])
    inner[1] = 0x11
    ext_b = ext_region.encode()
    payload = bytearray()
    payload.append(0x0a)
    payload.append(len(field1))
    payload.extend(field1)
    payload.append(0x12)
    payload.append(0x8e); payload.append(0x01)
    payload.extend(inner)
    payload.append(0x18); payload.append(0x02)
    payload.append(0x22); payload.append(len(ext_b))
    payload.extend(ext_b)
    return _struct.pack('>I', len(payload)) + bytes(payload)

def HELLXbuild_emote(bot_uid: int, target_uid: int, emote_id: int, key, iv) -> bytes:
    fields = {
        1: 21,
        2: {
            1: int(target_uid),
            2: emote_id,
            5: {
                1: int(target_uid),
                3: int(emote_id),
            },
        },
    }
    proto_hex = HELLXcreate_proto(fields).hex()
    return HELLXgenerate_packet(proto_hex, '0515', key, iv)

def HELLXbuild_create_squad(region: str, version: str, key, iv) -> bytes:
    fields = {
        1: 1,
        2: {
            2: bytes.fromhex("010304161d"),
            3: 15,
            4: 3,
            5: "en",
            8: [
                {1: "IDC1", 2: 80, 3: region},
                {1: "IDC2", 2: 53, 3: region},
                {1: "IDC3", 2: 124, 3: region},
                {1: "IDC4", 2: 233, 3: region},
            ],
            9: 1,
            10: bytes.fromhex("01030407090a0b12161920 1d27".replace(" ","")),
            11: 1,
            13: 1,
            14: {
                1: "08FFF3BE913CA75B02052F0222220000009600020094003C3A33107913D91078467625141101040ff77f2020ca3ca4f969cbc4e50000004f0e0e0801cacfa16d",
                2: 476,
                3: bytes.fromhex(
                    "7658515c16050804e550454504094c53570c0702525404025607060803"
                    "544f01055204575f5b025404131e0001485948464e1f001d011d16050a"
                    "4e1c447b5c5345707c514f6572401f5c5b40075541436b5c65640d1b03"
                    "4b1d055e771b670d4a7b024755466276195d5d404c4c4753630404000511"
                    "06054c59727272704056575b194178420d1d79735f6454686463055257"
                    "704e0a15084d5f4c6d0d774477025e6164735f5c0d775f4659505e4a"
                    "454e4c6d59440b1303464c5f5372 4d5d74554a024d6d767759 6e4a"
                    "7d5207677a59575487600d1208480d4c59464e01775f 584c4d754246"
                    "6d71655e4941514d525d595c5b435b0c1305 0d4852 7c5d7d1d6672"
                    "57025853770d5e627e7a5d564d 7c470e6763077109160744025f7c49"
                    "55024e0c7069741c656a53664657514802775f6048680008170c4e5c53"
                    "0876 4c41044d530d7e00097967006665000263 5c64717a78091b0007"
                    "4a7b417777067750 0a58657247410d5f665b624173574f6671474f59"
                    "4f0f14034c4752754c6c7954795903077e5b5643 5c04726579697e"
                    "054172 7e550a".replace(" ","")
                ),
                4: "zW\\R",
                6: 11,
                7: bytes.fromhex("14720467 6c64621613".replace(" ","")),
                8: version,
                9: 3,
                10: 2,
                11: "\x03bbSQ62iz591xAdV2KyoVlTtsUZkv08Zr7Qr3yXm7+zu4THgJA8epXNyEzy1ySZuypve2AhTz0XL1xQmE0f+gIBTN1dT5v3FFqy/GNyxyaVBm6o9+4/7rXepN29ERNRafz9Ke5spj1yt7bIV3/g/x5KKpfAQAiWKJmwgKSGHu2kOkH8koNaqLmO9m8+4LPzA9HaqzDbdLM1FZiGEIvVcZYBb5zW+lexeMkXPFPX62d1kOEBVy7/+DEKJUIIUoiyxGiPgZphr8JOpmYj65gOaIlnteZHAykqwuxeVNu8Y3UTGpjzalKkDaVY7YUBctOH8wGrrH+5WybIdXDGLrmjR5k3QzG6s3hkNGAOoeAGg1hWWQCsMMduk3dQvx1TI3nIpU77TV5WRz9Hgs5qgQr8deHPnAGdXYu3kehknt44WuRavs3PCsq+ylc2/n0IIGzeWfXfMiE5cUaQ/mqocMmUBYA9gBQGjPE+uTVcCM0h+a0OUqwQma5kCWUPoZ++ZFBGgMZYOxT8QWz2r7yvG+bghm2IjuHZRm0sh2XdkPjLrTfYRy3qdBGt8CRkmaBF55/bzmvNewX8obZtriQ0sZxnnhcDYjbx2M",
            },
            19: 324,
            21: bytes.fromhex("374f5219"),
            24: [
                {1: 3, 2: 391}, {1: 4, 2: 385}, {1: 5, 2: 192},
                {1: 29, 2: 204}, {1: 22, 2: 115}, {1: 14, 2: 175}, {1: 21},
            ],
            27: {7: 51},
        },
    }
    proto_hex = HELLXcreate_proto(fields).hex()
    return HELLXgenerate_packet(proto_hex, '0515', key, iv)

def HELLXbuild_change_squad_size(grp_to: int, key, iv) -> bytes:
    fields = {
        1: 17,
        2: {
            1: 6728454010,
            2: 1,
            3: grp_to - 1,
            4: 15,
            5: "\x01\x03\x04\x16\x1d",
            8: 1,
        },
    }
    proto_hex = HELLXcreate_proto(fields).hex()
    return HELLXgenerate_packet(proto_hex, '0515', key, iv)

def HELLXbuild_squad_info_request(bot_uid: int, key, iv) -> bytes:
    fields = {1: 15, 2: {1: int(bot_uid), 2: 1}}
    proto_hex = HELLXcreate_proto(fields).hex()
    return HELLXgenerate_packet(proto_hex, '0515', key, iv)

def HELLXbuild_ghost_msg(owner_id: int, bot_uid: int, secret_code: str, message: str, key, iv) -> bytes:
    import time as _t
    fields = {
        1: 61,
        2: {
            1: int(owner_id),
            2: {
                1: int(owner_id),
                2: int(bot_uid),
                3: message,
                5: 12,
                6: 15,
                7: 1,
                8: {2: 1, 3: 1},
                9: 3,
            },
            3: str(secret_code),
        },
    }
    proto_hex = HELLXcreate_proto(fields).hex()
    return HELLXgenerate_packet(proto_hex, '0515', key, iv)

async def HELLXbuild_dm_message(bot_uid: int, target_uid: int, message: str, key, iv) -> bytes:
    import time as _t
    fields = {
        1: 1,
        2: {
            1: int(bot_uid),
            2: int(target_uid),
            3: 2,
            4: message,
            5: int(_t.time()),
            7: 6,
            9: {
                1: "HELLX",
                2: await get_randm_avatar(),
                4: 330,
                5: 910050002,
                13: {},
                14: {1: int(bot_uid), 3: {}},
                18: {1: int(bot_uid), 3: 1, 4: {}},
            },
            10: "en",
            13: {2: 1, 3: 1},
            14: {},
        },
    }
    proto_hex = HELLXcreate_proto(fields).hex()
    return HELLXgenerate_packet(proto_hex, '1215', key, iv)

async def HELLXequip_emote(jwt_token: str, login_url: str = None) -> bool:
    import aiohttp as _aiohttp
    import ssl as _ssl
    base = (login_url or "https://clientbp.ppmainecoonghj.com").rstrip("/")
    url = f"{base}/ChooseEmote"
    host = base.split("//", 1)[-1].split("/", 1)[0]
    headers = {
        "Accept-Encoding": "gzip",
        "Authorization": f"Bearer {jwt_token}",
        "Connection": "Keep-Alive",
        "Content-Type": "application/x-www-form-urlencoded",
        "Expect": "100-continue",
        "Host": host,
        "ReleaseVersion": "OB55",
        "User-Agent": "UnityPlayer/2022.3.47f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)",
        "X-GA": "v1 1",
        "X-Unity-Version": "2022.3.47f1",
    }
    data = bytes.fromhex("673b1ad08072c36b91c0749256091802")
    ctx = _ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = _ssl.CERT_NONE
    try:
        async with _aiohttp.ClientSession() as s:
            async with s.post(url, headers=headers, data=data, ssl=ctx, timeout=8) as r:
                return r.status == 200
    except Exception:
        return False
