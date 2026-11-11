import os
import asyncio
import shutil
import sys
import struct
import time
import re
from utils import HELLXload_accounts, HELLXdefault_headers, HELLXlog
from auth import (
    HELLXgenerate_access,
    HELLXbuild_major_login,
    HELLXmajor_login,
    HELLXget_login_data,
    HELLXdecode_major_login,
    HELLXdecode_login_data,
    HELLXbuild_auth_startup,
    HELLXbuild_final_token,
    HELLXbuild_final_token_bytes,
    HELLXbuild_chat_auth_token,
    HELLXbuild_fnl_token_ghost,
    HELLXbuild_post_auth_packets,
    HELLXbuild_ping_packet,
    HELLXbuild_accept_invite,
    HELLXbuild_voice_step1,
    HELLXbuild_voice_auth,
    HELLXbuild_voice_auth_device,
    HELLXbuild_voice_ping,
    HELLXbuild_voice_stat_report,
    HELLXbuild_voice_broadcast_sub,
    HELLXbuild_voice_join,
    HELLXbuild_voice_custom,
    HELLXparse_voice_custom_response,
    HELLXbuild_voice_redirect,
    HELLXbuild_chat_auth,
    HELLXbuild_chat_global_auth,
    HELLXbuild_chat_message,
    HELLXbuild_leave_team,
    HELLXbuild_chat_close,
    HELLXfetch_version,
    HELLXfetch_city,
    _VOICE_BASE_HEX,
    HELLXbuild_emote,
    HELLXbuild_create_squad,
    HELLXbuild_change_squad_size,
    HELLXbuild_squad_info_request,
    HELLXbuild_ghost_msg,
    HELLXbuild_dm_message,
    HELLXbuild_join_sq,
    HELLXequip_emote,
)
from network import HELLXconnect_online, HELLXping_loop, HELLXread_loop
from voice import HELLXextract_garena_voice_data, HELLXextract_voice_from_tcp
from proto import HELLXdecode_proto

def _yt_dlp_command():
    # Prefer module form so same interpreter is used (venv-safe)
    return [sys.executable, "-m", "yt_dlp"]


def _yt_dlp_base_args(search=False):
    """Fast, bounded YouTube extraction/download settings for mobile devices."""
    args = [
        "--no-playlist",
        "--geo-bypass",
        "--no-warnings",
        "--no-progress",
        "--socket-timeout", "9" if search else "20",
        "--retries", "1",
        "--fragment-retries", "1",
        "--extractor-retries", "1",
    ]
    if search:
        # Search results only need title/channel/id. Flat extraction avoids a
        # second round of per-video metadata requests and is much quicker.
        args += ["--flat-playlist"]
    else:
        # Parallel DASH/HLS fragment fetching helps slower mobile connections.
        args += ["--concurrent-fragments", "4", "--http-chunk-size", "10M"]
    args += ["--extractor-args", "youtube:player_client=android"]
    return args


def _yt_dlp_run(cmd, timeout=40):
    """Run yt-dlp; raise clean short errors (never dump full argv)."""
    import subprocess
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise Exception("YouTube timed out. Check network / try again.")
    except FileNotFoundError:
        raise Exception("yt-dlp not found. Run: pip install -U yt-dlp")


def _ffmpeg_executable():
    """Resolve ffmpeg: PATH → Termux/Linux paths → local → imageio_ffmpeg."""
    import os as _os
    which = shutil.which("ffmpeg")
    if which and _os.path.isfile(which):
        return which
    for p in (
        "/data/data/com.termux/files/usr/bin/ffmpeg",
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
    ):
        if _os.path.isfile(p):
            return p
    here = _os.path.dirname(_os.path.abspath(__file__))
    for rel in (
        "ffmpeg.exe", "ffmpeg",
        _os.path.join("bin", "ffmpeg.exe"), _os.path.join("bin", "ffmpeg"),
        _os.path.join("ffmpeg", "bin", "ffmpeg.exe"), _os.path.join("ffmpeg", "bin", "ffmpeg"),
        _os.path.join("ffmpeg", "ffmpeg.exe"), _os.path.join("ffmpeg", "ffmpeg"),
    ):
        p = _os.path.normpath(_os.path.join(here, rel))
        if _os.path.isfile(p):
            return p
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and _os.path.isfile(exe):
            return exe
    except Exception:
        pass
    raise FileNotFoundError(
        "ffmpeg not found. On Termux run: pkg install ffmpeg | "
        "On PC: pip install imageio-ffmpeg OR install ffmpeg to PATH"
    )


def _opusenc_executable():
    """Optional opusenc. Returns None on Termux/Linux if missing (ffmpeg libopus used instead)."""
    import os as _os
    candidates = []
    which = shutil.which("opusenc")
    if which:
        candidates.append(which)
    here = _os.path.dirname(_os.path.abspath(__file__))
    for rel in (
        _os.path.join(here, "opus", "opusenc.exe"),
        _os.path.join(here, "opus", "opusenc"),
        _os.path.join(here, "..", "opus", "opusenc.exe"),
        _os.path.join(here, "..", "opus", "opusenc"),
        _os.path.join(here, "opusenc.exe"),
        _os.path.join(here, "opusenc"),
        "/data/data/com.termux/files/usr/bin/opusenc",
        "/usr/bin/opusenc",
    ):
        candidates.append(rel)
    for p in candidates:
        if not p:
            continue
        p = _os.path.normpath(p)
        if not _os.path.isfile(p):
            continue
        if p.lower().endswith(".exe") and _os.name != "nt":
            continue
        return p
    return None



def _ogg_opus_frames(stream):
    """Yield complete Opus packets from an Ogg stream, including cross-page packets."""
    buf = b""
    packet_buffer = bytearray()
    while True:
        chunk = stream.read(8192)
        if not chunk:
            buf, frames = _parse_ogg_buf(
                buf, drain_all=True, packet_buffer=packet_buffer
            )
            yield from frames
            break
        buf, frames = _parse_ogg_buf(
            buf + chunk, packet_buffer=packet_buffer
        )
        yield from frames


def _ogg_opus_frames_bytes(data: bytes):
    """Extract complete Opus packets from a complete Ogg/Opus byte string."""
    _, frames = _parse_ogg_buf(data, drain_all=True, packet_buffer=bytearray())
    yield from frames


def _parse_ogg_buf(buf: bytes, drain_all=False, packet_buffer=None):
    """Parse Ogg pages using the lacing table; each returned item is one full packet."""
    frames = []
    packet = packet_buffer if packet_buffer is not None else bytearray()

    while True:
        pos = buf.find(b"OggS")
        if pos < 0:
            buf = buf[-3:] if len(buf) >= 3 else buf
            break
        if pos:
            buf = buf[pos:]
        if len(buf) < 27:
            break
        if buf[4] != 0:  # Ogg bitstream structure version
            buf = buf[1:]
            continue

        n_segs = buf[26]
        header_end = 27 + n_segs
        if len(buf) < header_end:
            break
        seg_table = buf[27:header_end]
        page_size = sum(seg_table)
        page_end = header_end + page_size
        if len(buf) < page_end:
            break

        page_data = buf[header_end:page_end]
        buf = buf[page_end:]
        offset = 0
        for segment_size in seg_table:
            segment = page_data[offset:offset + segment_size]
            offset += segment_size
            packet.extend(segment)
            # A lacing value below 255 terminates the current Ogg packet.
            if segment_size < 255:
                completed = bytes(packet)
                packet.clear()
                if completed and not completed.startswith((b"OpusHead", b"OpusTags")):
                    frames.append(completed)

    return buf, frames
class HELLXBot:
    def __init__(self, uid, password):
        self.uid = uid
        self.password = password
        self.key = b'Yg&tc%DEuh6%Zc^8'
        self.iv = b'6oyZDr22E3ychjM%'
        self.token = None
        self.login_url = None
        self.timestamp = None
        self.online_ip = "98.98.162.30"
        self.online_port = 39699
        self.chat_ip = None
        self.chat_port = None
        self.voice_ip = None
        self.voice_port = None
        self.voice_region_id = None
        self.login_error = None
        self.login_ok = False   
        self.voice_secret = None      
        self.voice_chat_key = None
        self.chat_region_id = None
        self.team_owner_uid = None
        self.region_prefix = "ME"
        self.ext_region = "ME"
        self._sdk_verify_domain = "ff.rtc.grtc.garenanow.com"
        self._validate_ips = ["47.254.135.114", "47.91.95.237"]
        self._leave_after_join = False
        self.writer = None
        self._voice_writer = None
        self._voice_reader = None
        self._voice_ping_task = None
        self._voice_connect_task = None
        self._processed_invite_code = None
        self.voice_candidates = []
        self._capture_count = 0
        self._capture_limit = 0
        self._chat_writer = None
        self._chat_reader = None
        self._chat_buffer = bytearray()
        self._chat_reconnect_task = None
        self._chat_reconnect_lock = asyncio.Lock()
        self._team_chat_auth_sent = False
        self._telegram_team_code = None
        self.opus_bitrate = 18000
        self.opus_samplerate = 48000
        self.opus_channels = 1
        self.voice_ssrc = b'\x0c\x43\x03\x3e'
        self._voice_f5 = 0
        self._voice_f3 = 0x13e6
        self._voice_heartbeat_interval = 5.0
        self._voice_ip = None
        self._voice_port = None
        self._udp_task = None
        self._current_url = None
        self._current_ogg = None
        self._search_results = []
        self._search_query = ""
        self._search_page = 0
        # Per-account short-lived cache prevents repeated YouTube lookups for
        # the same search while avoiding stale results for long periods.
        self._search_cache = {}
        self._voice_ssrc_refresh = False
        self._voice_tcp_rx_count = 0
        self._manual_stop_requested = False
        self._track_title = ""
        self._track_channel = ""
        self._track_total_frames = 0
        self._track_current_frame = 0
        self._progress_task = None
        self._stopped_frame = 0
        self._volume = 100
        self._lyrics_enabled = False
        self._lyrics_data = []      
        self._lyrics_task = None
    async def _handle_tcp_data(self, data):
        buffer = bytearray(data)
        pos = 0
        while pos < len(buffer) - 5:
            opcode = buffer[pos]
            length = struct.unpack('>I', buffer[pos+1:pos+5])[0]
            if 0 < length < 200000 and pos + 5 + length <= len(buffer):
                payload = bytes(buffer[pos+5:pos+5+length])
                try:
                    proto_data = HELLXdecode_proto(payload)
                    if not proto_data:
                        pos += 5 + length
                        continue
                    field5 = proto_data.get('5')
                    if isinstance(field5, dict):
                        code = field5.get('8')
                        owner_uid = field5.get('1', self.uid)
                        if code and isinstance(code, str) and '_' in code:
                            if code != self._processed_invite_code:
                                self._processed_invite_code = code
                                accept_pkt = HELLXbuild_accept_invite(owner_uid, code, self.key, self.iv)
                                if self.writer:
                                    self.writer.write(accept_pkt)
                                    await self.writer.drain()
                                    HELLXlog("TEAM", f"Invitation accepted. code={code}")
                    if not self.voice_region_id and isinstance(field5, dict):
                        region_id = field5.get('17')
                        if region_id:
                            self.voice_region_id = int(region_id)
                            self.chat_region_id = int(self.voice_region_id / 256 + 0.5) * 256
                            self.team_owner_uid = int(field5.get('1', self.uid))
                            self._team_chat_auth_sent = False
                            HELLXlog("TEAM", f"region_id={self.voice_region_id} owner={self.team_owner_uid}")
                            chat_key = field5.get('31')
                            if chat_key:
                                self.voice_chat_key = str(chat_key)
                            if getattr(self, '_joining', False):
                                self._join_success = True
                            asyncio.create_task(self._connect_chat())
                            if not self._voice_connect_task or self._voice_connect_task.done():
                                self._voice_connect_task = asyncio.create_task(self._voice_connect())
                            # stay in squad until song ends (no silent leave)
                    if isinstance(field5, dict):
                        sender_uid_online = str(field5.get('1', ''))
                        message_online = field5.get('4', '')
                        if isinstance(message_online, str) and message_online.strip() and sender_uid_online != str(self.uid):
                            HELLXlog("CHAT", f"[online][{sender_uid_online}]: {message_online}")
                    sq_target = getattr(self, '_pending_squad_target', None)
                    if sq_target:
                        sq_data = proto_data.get('5')
                        if isinstance(sq_data, dict):
                            items = sq_data if isinstance(sq_data, list) else [sq_data]
                        elif isinstance(sq_data, list):
                            items = sq_data
                        else:
                            items = []
                        for _it in items:
                            if not isinstance(_it, dict): continue
                            _entry = _it
                            if '17' not in _entry or '31' not in _entry:
                                _inner = _it.get('3', {})
                                if isinstance(_inner, dict) and '17' in _inner and '31' in _inner:
                                    _entry = _inner
                            if '17' in _entry and '31' in _entry:
                                _squad_code = str(_entry.get('31', ''))
                                if '_' in _squad_code:
                                    self._pending_squad_target = None
                                    async def _send_squad_code(_code=_squad_code, _tgt=sq_target):
                                        try:
                                            import time as _t
                                            pkt = await HELLXbuild_dm_message(int(self.uid), int(_tgt), f"[27EBF5]TeAm CreAtEd , CopY cOde BeLoW :\n[5427F5]{_code}", self.key, self.iv)
                                            if self._chat_writer and not self._chat_writer.transport.is_closing():
                                                self._chat_writer.write(pkt)
                                                await self._chat_writer.drain()
                                        except Exception:
                                            pass
                                    asyncio.create_task(_send_squad_code())
                                    break
                except Exception:
                    pass
                pos += 5 + length
            else:
                pos += 1
    async def _voice_connect(self):
        if not self.voice_region_id:
            HELLXlog("VOICE", "ERROR: No region_id")
            return
        self._voice_f5 = 0
        self._voice_f3 = 0x13e6
        import re as _re
        import aiohttp as _aiohttp
        import struct as _st2

        async def _read_voice_frame(reader, timeout):
            header = await asyncio.wait_for(reader.readexactly(4), timeout)
            frame_length = _st2.unpack('>I', header)[0]
            if frame_length <= 0 or frame_length > 65536:
                raise ValueError(f"invalid voice frame length: {frame_length}")
            return await asyncio.wait_for(reader.readexactly(frame_length), timeout)

        sdk_token = None
        redirect_ip, redirect_port = None, None
        SDK_VERIFY_URL = f"https://{self._sdk_verify_domain}/sdk/sdk_verify"
        _SDK_VERIFY_PAYLOAD = bytes.fromhex(
            '0a8e010800100b180122074f6e65506c75732a013930cc80868c023a0961726d3634'
            '2d76386142004a2439313864346563382d383733332d343930622d626334362d643132'
            '666139396337383238522a464644353846423446373646363438433241354532314542'
            '4346413341414538314234433942374439375a05766f69636562064e45323231316802'
            '720471636f6d12800160ad4251d2f821e2701e5e1d8b607d2b34dcb0c512300ac3e5839'
            '6155780dc64686b20d05581c038ae28539fc3bc21ced330e31721e18e6c626972829f'
            '6878cb8ec7d95f2f7391bd25f9d7296f09f56f9bc5bccabaf10f09b58c39dc02c08995'
            'd6abe727d93bcea4123da86ad42f6500fa68e74ddc2ed2cb7af0aadd22d2ec93180120'
            '063800'
        )

        def _parse_sdk_response(data):
            nonlocal sdk_token, redirect_ip, redirect_port
            if len(data) < 4:
                return
            _vproto = HELLXdecode_proto(data)
            _f5 = _vproto.get('5')
            _candidates = _f5 if isinstance(_f5, list) else ([_f5] if _f5 else [])
            for _r in _candidates:
                if isinstance(_r, bytes):
                    _r = HELLXdecode_proto(_r)
                if isinstance(_r, dict):
                    _rip = _r.get('1')
                    _rport = _r.get('2')
                    if isinstance(_rip, str) and '.' in _rip and _rport:
                        redirect_ip = _rip
                        redirect_port = int(_rport)
                        HELLXlog("VOICE", f"SDK verify redirect: {redirect_ip}:{redirect_port}")
                        break
            import re as _re2
            if not redirect_ip:
                m_ip = _re2.search(rb'([\d]{1,3}\.[\d]{1,3}\.[\d]{1,3}\.[\d]{1,3})', data)
                m_port = _re2.search(rb'\x10([\x80-\xff]?.)', data[data.find(b'\x0a\x0d') + 15:] if b'\x0a\x0d' in data else b'')
                if m_ip:
                    redirect_ip = m_ip.group(1).decode()
                    HELLXlog("VOICE", f"SDK verify redirect (regex): {redirect_ip}")
                if not redirect_port and m_port:
                    _pb = m_port.group(1)
                    if len(_pb) == 1:
                        redirect_port = _pb[0]
                    elif len(_pb) == 2 and _pb[0] & 0x80:
                        redirect_port = (_pb[0] & 0x7f) | (_pb[1] << 7)
            m_opus = _re2.search(rb'OPUS_BITRATE[\x00-\x20]{0,8}(\d{4,6})', data)
            if m_opus:
                _brate = int(m_opus.group(1).decode())
                if 8000 <= _brate <= 64000:
                    self.opus_bitrate = _brate
                    HELLXlog("VOICE", f"OPUS_BITRATE from server: {_brate}")
            _pos = 0
            while _pos < len(data) - 2:
                if data[_pos] == 0x12:
                    _p2 = _pos + 1; _vlen = 0; _shift = 0
                    while _p2 < len(data):
                        _b = data[_p2]; _vlen |= (_b & 0x7F) << _shift; _p2 += 1; _shift += 7
                        if not (_b & 0x80): break
                    if _vlen == 128 and _p2 + 128 <= len(data):
                        sdk_token = data[_p2:_p2 + 128]
                        break
                _pos += 1
            HELLXlog("VOICE", f"SDK token: {sdk_token.hex()[:32] if sdk_token else 'None'}")

        try:
            _ssl_ctx = __import__('ssl').create_default_context()
            _ssl_ctx.check_hostname = False
            _ssl_ctx.verify_mode = __import__('ssl').CERT_NONE
            async with _aiohttp.ClientSession() as _sess:
                async with _sess.post(
                    SDK_VERIFY_URL,
                    data=_SDK_VERIFY_PAYLOAD,
                    headers={
                        "Host": self._sdk_verify_domain,
                        "Accept": "*/*",
                        "Accept-Encoding": "identity",
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Content-Length": str(len(_SDK_VERIFY_PAYLOAD)),
                    },
                    ssl=_ssl_ctx,
                    timeout=_aiohttp.ClientTimeout(total=8)
                ) as _resp:
                    _rbody = await _resp.read()
                    HELLXlog("VOICE", f"SDK verify HTTPS: status={_resp.status} len={len(_rbody)}")
                    if _resp.status == 200 and len(_rbody) > 4:
                        _parse_sdk_response(_rbody)
        except Exception as e:
            HELLXlog("VOICE", f"SDK verify HTTPS failed: {e}, trying TCP fallback...")

        if not redirect_ip:
            try:
                import socket as _sock
                import struct as _st3
                _infos = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: _sock.getaddrinfo(self._sdk_verify_domain, 8012, _sock.AF_INET)
                )
                _tcp_ips = list(dict.fromkeys(info[4][0] for info in _infos))
                HELLXlog("VOICE", f"SDK verify TCP fallback: DNS={_tcp_ips}")
                _tcp_pkt = _st3.pack('>I', len(_SDK_VERIFY_PAYLOAD)) + _SDK_VERIFY_PAYLOAD
                for _tip in _tcp_ips:
                    try:
                        _tr, _tw = await asyncio.wait_for(
                            asyncio.open_connection(_tip, 8012), timeout=5.0)
                        _tw.write(_tcp_pkt)
                        await _tw.drain()
                        _tbody = b""
                        try:
                            _chunk = await asyncio.wait_for(_tr.read(65536), timeout=8.0)
                            if _chunk:
                                _tbody = _chunk
                                while True:
                                    try:
                                        _more = await asyncio.wait_for(_tr.read(65536), timeout=2.0)
                                        if not _more: break
                                        _tbody += _more
                                    except asyncio.TimeoutError:
                                        break
                        except asyncio.TimeoutError:
                            pass
                        try:
                            _tw.close()
                        except Exception:
                            pass
                        if _tbody:
                            HELLXlog("VOICE", f"SDK verify TCP: {_tip}:8012 RX {len(_tbody)}B")
                            _parse_sdk_response(_tbody[4:] if len(_tbody) > 4 else _tbody)
                            if redirect_ip:
                                break
                    except Exception as _te:
                        HELLXlog("VOICE", f"SDK verify TCP {_tip} failed: {_te}")
            except Exception as e:
                HELLXlog("VOICE", f"SDK verify TCP fallback failed: {e}")

        if not redirect_ip or not redirect_port:
            HELLXlog("VOICE", "ERROR: No redirect from SDK verify")
            return
        HELLXlog("VOICE", f"Step2: {redirect_ip}:{redirect_port}")
        try:
            r2, w2 = await asyncio.wait_for(
                asyncio.open_connection(redirect_ip, redirect_port), timeout=5.0)
        except Exception as e:
            HELLXlog("VOICE", f"Step2 failed: {e}")
            return
        redir_pkt = HELLXbuild_voice_redirect(self.uid, self.voice_region_id, self.region_prefix, self.ext_region)
        HELLXlog("VOICE", f"Step2 TCP CONNECT: {redirect_ip}:{redirect_port}")
        HELLXlog("VOICE", f"Step2 REQUEST ({len(redir_pkt)}B): {redir_pkt.hex()}")
        w2.write(redir_pkt)
        await w2.drain()
        HELLXlog("VOICE", "Step2: TX sent")
        voice_ip, voice_port = None, None
        try:
            header2 = await asyncio.wait_for(r2.readexactly(4), timeout=5.0)
            response_length = struct.unpack('>I', header2)[0]
            if response_length <= 0 or response_length > 65536:
                raise ValueError(f"invalid Step2 response length: {response_length}")
            resp2 = header2 + await asyncio.wait_for(
                r2.readexactly(response_length), timeout=5.0
            )
            if resp2:
                HELLXlog("VOICE", f"Step2 RESPONSE ({len(resp2)}B): {resp2.hex()}")
                data = resp2[4:]
                proto = HELLXdecode_proto(data)
                ip_val = proto.get('1')
                port_val = proto.get('2')
                if isinstance(ip_val, str) and '.' in ip_val:
                    voice_ip = ip_val
                if isinstance(port_val, int):
                    voice_port = port_val
                HELLXlog("VOICE", f"UDP VOICE TARGET: {voice_ip}:{voice_port} (audio UDP port={voice_port + 2 if voice_port else None})")
        except asyncio.TimeoutError:
            HELLXlog("VOICE", "Step2: timeout")
        w2.close()
        if not voice_ip or not voice_port:
            HELLXlog("VOICE", "ERROR: No voice IP from redirect")
            return
        HELLXlog("VOICE", f"Step3: {voice_ip}:{voice_port}")
        try:
            r3, w3 = await asyncio.wait_for(
                asyncio.open_connection(voice_ip, voice_port), timeout=5.0)
        except Exception as e:
            HELLXlog("VOICE", f"Step3 failed: {e}")
            return
        self._voice_writer = w3
        self._voice_reader = r3
        auth3 = HELLXbuild_voice_auth(self.uid, self.voice_region_id, voice_port, self.region_prefix)
        w3.write(auth3[:4])
        await w3.drain()
        w3.write(auth3[4:])
        await w3.drain()
        HELLXlog("VOICE", "Step3: TX auth type=7")
        try:
            resp3 = await _read_voice_frame(r3, 3.0)
            if resp3:
                _p = HELLXdecode_proto(resp3)
                HELLXlog("VOICE", f"Step3 resp: {_p}")
                self._voice_f3 = int(_p.get('3', 0x13e6))
                f5_value = _p.get('5', _p.get('13', 0))
                if isinstance(f5_value, dict):
                    f5_value = f5_value.get('1', 0)
                if isinstance(f5_value, list):
                    f5_value = f5_value[0] if f5_value else 0
                self._voice_f5 = int(f5_value) & 0xFFFFFFFF
                HELLXlog("VOICE", f"f5=0x{self._voice_f5:08x} f3=0x{self._voice_f3:04x}")
        except (asyncio.TimeoutError, TypeError, ValueError):
            pass
        if self._voice_f5 == 0:
            HELLXlog("VOICE", "f5=0 detected, wrong MCU session. Sending warning to chat...")
            asyncio.create_task(self._send_chat_message(
                "[F52727]Wrong IPs detected, please wait, i will handle!\n"
                "[A627F5]If voice still not coming, please contact:\n"
                "[27EBF5]Make bot leave and create a new team -> invite it.\n"
                "[F227F5]Leave command => !leave or /help"
            ))
            try:
                w3.close()
                await w3.wait_closed()
            except Exception:
                pass
            self._voice_writer = None
            self._voice_reader = None
            await asyncio.sleep(3)
            self._voice_connect_task = asyncio.create_task(self._voice_connect())
            return
        custom = HELLXbuild_voice_custom(self.uid, self.voice_region_id, mcu_ip=voice_ip, region_prefix=self.region_prefix)
        w3.write(custom[:4])
        await w3.drain()
        w3.write(custom[4:])
        await w3.drain()
        HELLXlog("VOICE", "Step3: TX custom binary")
        try:
            resp4 = await _read_voice_frame(r3, 3.0)
            if resp4:
                HELLXlog("VOICE", f"Custom resp: {resp4.hex()[:80]}")
                raw = resp4[4:] if resp4[:4] != b'\xfe\xff\xff\x7f' else resp4
                idx = raw.find(b'\xfe\xff\xff\x7f')
                if idx != -1:
                    ts_idx = raw.find(b'\x17\x76', idx)
                    if ts_idx != -1 and ts_idx + 6 <= len(raw):
                        self.voice_session_ts = raw[ts_idx+2:ts_idx+6]
                        HELLXlog("VOICE", f"session_ts: {self.voice_session_ts.hex()}")
        except asyncio.TimeoutError:
            pass
        if self._voice_ping_task:
            self._voice_ping_task.cancel()
        self._voice_ping_task = asyncio.create_task(
            self._voice_ping_loop(w3, r3)
        )
        self._voice_ip = voice_ip
        self._voice_port = voice_port
        async def _voice_tcp_reader():
            try:
                while True:
                    try:
                        data = await _read_voice_frame(r3, 30.0)
                    except (asyncio.IncompleteReadError, ConnectionError):
                        HELLXlog("VOICE", "TCP: Server closed connection!")
                        if self._udp_task and not self._udp_task.done():
                            self._udp_task.cancel()
                        break
                    self._voice_tcp_rx_count += 1
                    if self._voice_tcp_rx_count <= 3 or self._voice_tcp_rx_count % 100 == 0:
                        HELLXlog("VOICE", f"TCP RX: packet={self._voice_tcp_rx_count} size={len(data)}B")
                    try:
                        p = HELLXdecode_proto(data)
                        inner = p.get('1', {})
                        pkt_type = inner.get('1', 0) if isinstance(inner, dict) else 0
                        field2 = p.get('2', 0)
                        if pkt_type == 0x0b and field2:
                            HELLXlog("VOICE", f"TCP: 0x0b received, re-sending auth type=7")
                            self._voice_ssrc_refresh = True
                            async def _do_reauth():
                                auth3 = HELLXbuild_voice_auth(self.uid, self.voice_region_id, voice_port, self.region_prefix)
                                w3.write(auth3[:4]); await w3.drain()
                                w3.write(auth3[4:]); await w3.drain()
                                custom = HELLXbuild_voice_custom(self.uid, self.voice_region_id, mcu_ip=voice_ip, region_prefix=self.region_prefix)
                                w3.write(custom[:4]); await w3.drain()
                                w3.write(custom[4:]); await w3.drain()
                                HELLXlog("VOICE", "TCP: Re-auth sent")
                            asyncio.create_task(_do_reauth())
                    except Exception:
                        pass
            except Exception as e:
                HELLXlog("VOICE", f"TCP reader error: {e}")
        asyncio.create_task(_voice_tcp_reader())
        HELLXlog("VOICE", f"Step3: Done. Streaming to {voice_ip}:{voice_port+2}")
    async def _leave_team(self):
        HELLXlog("TEAM", "Leaving team...")
        if self.writer and not self.writer.is_closing():
            try:
                leave_pkt = HELLXbuild_leave_team(int(self.uid), self.key, self.iv)
                self.writer.write(leave_pkt)
                await self.writer.drain()
            except Exception as leave_error:
                HELLXlog("TEAM", f"Online leave packet failed: {leave_error}")
        if self._chat_writer:
            try:
                close_pkt = HELLXbuild_chat_close(int(self.uid), self.key, self.iv)
                self._chat_writer.write(close_pkt)
                await self._chat_writer.drain()
            except Exception:
                pass
        if self._udp_task and not self._udp_task.done():
            self._udp_task.cancel()
        if self._progress_task and not self._progress_task.done():
            self._progress_task.cancel()
        if self._lyrics_task and not self._lyrics_task.done():
            self._lyrics_task.cancel()
        if self._voice_ping_task and not self._voice_ping_task.done():
            self._voice_ping_task.cancel()
        if self._voice_connect_task and not self._voice_connect_task.done():
            self._voice_connect_task.cancel()
        self.voice_region_id = None
        self.chat_region_id = None
        self.team_owner_uid = None
        self._team_chat_auth_sent = False
        self._telegram_team_code = None
        self.voice_chat_key = None
        self._processed_invite_code = None
        self._voice_ip = None
        self._voice_port = None
        self._voice_writer = None
        self._voice_reader = None
        self._current_ogg = None
        self._current_url = None
        self._track_title = ""
        self._track_channel = ""
        self._track_total_frames = 0
        self._track_current_frame = 0
        self._stopped_frame = 0
        self._search_results = []
        self._search_query = ""
        self._search_page = 0
        HELLXlog("TEAM", "Left team. Waiting for new invite...")
    def _chat_writer_open(self, writer=None):
        writer = self._chat_writer if writer is None else writer
        if writer is None:
            return False
        try:
            return not writer.is_closing()
        except Exception:
            try:
                return not writer.transport.is_closing()
            except Exception:
                return False

    def _schedule_chat_reconnect(self):
        task = self._chat_reconnect_task
        if task is None or task.done():
            try:
                self._chat_reconnect_task = asyncio.create_task(self._reconnect_chat())
            except RuntimeError:
                self._chat_reconnect_task = None

    async def _connect_chat(self):
        if not self.voice_region_id:
            return
        w = self._chat_writer
        if not self._chat_writer_open(w):
            self._team_chat_auth_sent = False
            HELLXlog("CHAT", "Squad chat socket unavailable; reconnect scheduled")
            self._schedule_chat_reconnect()
            return
        try:
            owner = self.team_owner_uid if self.team_owner_uid else int(self.uid)
            auth_pkt = HELLXbuild_chat_auth(owner, str(self.chat_region_id), self.key, self.iv)
            w.write(auth_pkt)
            await w.drain()
            self._team_chat_auth_sent = True
            HELLXlog("CHAT", f"Squad auth sent (owner={owner} region={self.chat_region_id})")
        except Exception as e:
            self._team_chat_auth_sent = False
            HELLXlog("CHAT", f"Squad chat auth failed: {e}; reconnect scheduled")
            if w is self._chat_writer:
                self._chat_writer = None
                self._chat_reader = None
            try:
                w.close()
            except Exception:
                pass
            self._schedule_chat_reconnect()
    async def _handle_dm(self, message: str, sender_name: str, sender_uid: str):
        try:
            msg = message.strip()
            if msg.startswith('/') and not msg.startswith('//'):
                msg = '!' + msg[1:]
            cmd = msg.lower().split()[0] if msg else ""
            args = msg.split()[1:] if len(msg.split()) > 1 else []
            HELLXlog("CMD", f"DM cmd={repr(cmd)} from={sender_uid}")
            reply_target = int(sender_uid)
            async def _dm_reply(text):
                try:
                    import time as _t
                    pkt = await HELLXbuild_dm_message(int(self.uid), reply_target, text, self.key, self.iv)
                    if self._chat_writer and not self._chat_writer.transport.is_closing():
                        self._chat_writer.write(pkt)
                        await self._chat_writer.drain()
                except Exception:
                    pass
            if cmd in ("!stop", "stop"):
                await _dm_reply("[F52727]Use /stop in the squad chat to stop music and leave the squad.")
                return
            if cmd == "!help":
                await _dm_reply(
                    "[5427F5]HeLLX BoT => CoMmAnDs\n"
                    "[F227F5]!play {url/keywords}\n"
                    "[F227F5]!stop => !resume\n"
                    "[F227F5]!dance {emote} [uid]\n"
                    "[F227F5]!evo_list => show evos\n"
                    "[F227F5]!3 , !5 , !6 => crEatE sQuAd\n"
                    "[F227F5]!ghost {code} {msg}\n"
                    "[27EBF5]Dev => @HeLlx_Hex"
                )
            else:
                asyncio.create_task(self._handle_command(message.strip(), sender_name, sender_uid))
        except Exception as e:
            HELLXlog("CMD", f"DM error: {e}")
    async def _handle_command(self, message: str, sender_name: str, sender_uid: str):
        try:
            msg = message.strip()
            if msg.startswith('/') and not msg.startswith('//'):
                msg = '!' + msg[1:]
            cmd = msg.lower().split()[0] if msg else ""
            args = msg.split()[1:] if len(msg.split()) > 1 else []
            HELLXlog("CMD", f"recv cmd={repr(cmd)} args={args} from={sender_uid}")
            if cmd == "!help":
                help_msg = (
                    f"[5427F5]HeLLo , {sender_name} => WeLcOmE !\n"
                    "[A627F5]» CoMmAnDs «\n"
                    "[F227F5]!play {url/keywords} => strEaM mUsIc\n"
                    "[F227F5]!search {keywords} => sEaRcH yOuTuBe\n"
                    "[F227F5]!select {n} , !next , !prev\n"
                    "[F227F5]!stop , !resume , !status\n"
                    "[F227F5]!sound {1-200} => vOlUmE\n"
                    "[F227F5]!dance {emote} [uid] => eVo dAncE\n"
                    "[F227F5]!evo_list => sHoW aLl EvOs\n"
                    "[F227F5]!3 , !5 , !6 => cReAtE sQuAd\n"
                    "[F227F5]!ghost {code} {msg} => gHoSt\n"
                    "[F227F5]!leave => lEaVe tEaM\n"
                    "[27EBF5]Dev => @HeLlx_Hex"
                )
                await self._send_chat_message(help_msg)
            elif cmd == "!play":
                if not args:
                    await self._send_chat_message("[F52727]Usage: /play [song name or YouTube URL]")
                    return
                HELLXlog("MUSIC", f"in-game /play request from={sender_uid}: {' '.join(args)[:100]}")
                lyrics = False
                play_args = args[:]
                if play_args and play_args[-1].lower() in ('on', 'off'):
                    lyrics = play_args.pop().lower() == 'on'
                query = " ".join(play_args)
                if query.startswith("http"):
                    await self._send_chat_message("[27EBF5]Downloading, please wait...")
                    asyncio.create_task(self._play_yt(query, lyrics=lyrics))
                else:
                    await self._send_chat_message(f"[27EBF5]Searching: {query}")
                    asyncio.create_task(self._search_and_play(query, 0, lyrics=lyrics))
            elif cmd == "!search":
                if not args:
                    await self._send_chat_message("[F52727]Usage: !search [keywords]")
                    return
                query = " ".join(args)
                self._search_query = query
                self._search_page = 0
                await self._do_search(query, 0)
            elif cmd == "!next":
                if not self._search_results:
                    await self._send_chat_message("[F52727]No search results. Use !search first.")
                    return
                if self._search_page >= len(self._search_results) - 1:
                    await self._send_chat_message("[27EBF5]Loading more results...")
                    await self._do_search(self._search_query, 0, offset=len(self._search_results))
                    return
                self._search_page += 1
                await self._show_search_page()
            elif cmd == "!previous":
                if not self._search_results:
                    await self._send_chat_message("[F52727]No search results. Use !search first.")
                    return
                if self._search_page <= 0:
                    await self._send_chat_message("[F52727][Off] Already at first result.")
                    return
                self._search_page -= 1
                await self._show_search_page()
            elif cmd == "!select":
                if not args or not args[0].isdigit():
                    await self._send_chat_message("[F52727]Usage: !select [number]")
                    return
                idx = int(args[0]) - 1
                if not self._search_results or idx < 0 or idx >= len(self._search_results):
                    await self._send_chat_message("[F52727]Invalid selection.")
                    return
                r = self._search_results[idx]
                self._track_title = r['title']
                self._track_channel = r.get('channel', '')
                await self._send_chat_message(f"[27EBF5]Loading: {r['title'][:50]}")
                asyncio.create_task(self._play_yt(r['url']))
            elif cmd == "!sound":
                if not args or not args[0].isdigit():
                    await self._send_chat_message("[F52727]Usage: !sound [1-200]")
                    return
                vol = int(args[0])
                if vol < 1 or vol > 200:
                    await self._send_chat_message("[F52727]Volume must be between 1 and 200.")
                    return
                self._volume = vol
                await self._send_chat_message(f"[27EBF5]Volume set to {vol}%\n[A627F5]Takes effect on next song.")
            elif cmd in ("!stop", "stop"):
                was_playing = bool(self._udp_task and not self._udp_task.done())
                was_in_team = bool(self.voice_region_id)
                await self._send_chat_message(
                    "[F52727]Playback stopped. Leaving the squad..."
                    if (was_playing or was_in_team)
                    else "[F52727]No active song or squad session."
                )
                await self.api_stop_and_leave()
            elif cmd in ("!resume", "resume"):
                if self._current_ogg and self._voice_ip:
                    sf = getattr(self, '_stopped_frame', 0)
                    await self._send_chat_message(f"[27EBF5]Resuming: {self._track_title}")
                    self._udp_task = asyncio.create_task(self._run_udp_then_leave(self._voice_ip, self._voice_port, self._current_ogg, sf))
                    if self._progress_task and not self._progress_task.done():
                        self._progress_task.cancel()
                    self._progress_task = asyncio.create_task(self._auto_progress_loop())
                else:
                    await self._send_chat_message("[F52727]Nothing to resume.")
            elif cmd == "!info":
                if not args:
                    await self._send_chat_message("[F52727]Usage: !info [youtube_url]")
                    return
                asyncio.create_task(self._yt_info(args[0]))
            elif cmd == "!dev":
                await self._send_chat_message(
                    "[5427F5]Developer: @HeLlx_Hex\n"
                    "[27EBF5]HELLX Voice Bot - Free Fire Music Bot"
                )
            elif cmd == "!status":
                if self._track_title and self._track_total_frames > 0:
                    frame = self._track_current_frame
                    total = self._track_total_frames
                    elapsed_s = int(frame * 0.02)
                    total_s = int(total * 0.02)
                    pct = min(frame / total, 1.0)
                    bar_len = 18
                    filled = int(bar_len * pct)
                    bar = "[27EBF5]" + "▓" * filled + "[5427F5]" + "░" * (bar_len - filled)
                    elapsed_str = f"{elapsed_s//60}:{elapsed_s%60:02d}"
                    total_str = f"{total_s//60}:{total_s%60:02d}"
                    playing = self._udp_task and not self._udp_task.done()
                    disc = ["◐","◓","◑","◒"][int(time.time()) % 4]
                    status = "[27EBF5]▶" if playing else "[F52727]⏸"
                    await self._send_chat_message(
                        f"{status} {disc} [5427F5]{self._track_title}\n"
                        f"[A627F5]{self._track_channel}\n"
                        f"{bar}\n"
                        f"[27EBF5]{elapsed_str} [F227F5]/ [27EBF5]{total_str}"
                    )
                else:
                    await self._send_chat_message("[A627F5]No music playing. Try !play [song name]")
            elif cmd in ("/leave", "!leave"):
                await self._leave_team()
            elif cmd == "!dance":
                if len(args) < 1:
                    await self._send_chat_message("[F52727]UsAgE => !dance {emote_name or id} [target_id]")
                    return
                _EVO_MAP = {
                    "scarlet":909039011,"tiger":909042008,"woodpecker":909042008,
                    "dreamland":909051003,"m60":909051003,"xm8":909000085,
                    "devil":909000090,"famas":909000090,"booyahday":909000098,"ump":909000098,
                    "m4a1":909033001,"m4":909033001,"mp40":909040010,"100lvl":909042007,
                    "throne":909000014,"heart":909000045,"love":909000045,
                    "laugh":909000002,"lol":909000002,"ak":909000063,"mp5":909033002,
                    "p90":909049010,"groza":909041005,"an94":909035012,"scar":909000068,
                    "m1887":909035007,"g18":909038012,"thompson":909038010,
                    "parafal":909045001,"namdam":909037011,
                }
                _ename = args[0].lower()
                _tid = args[1] if len(args) > 1 and args[1].isdigit() else self.uid
                _eid = _EVO_MAP.get(_ename)
                if _eid is None:
                    if _ename.isdigit():
                        _eid = int(_ename)
                    else:
                        await self._send_chat_message(f"[F52727]UnKnOwN EvO => {args[0]}\n[A627F5]tYpE !evo_list tO sEe AlL")
                        return
                async def _do_dance(_tid=_tid, _eid=_eid):
                    try:
                        await HELLXequip_emote(self.token, self.login_url)
                        if self.writer and not self.writer.transport.is_closing():
                            pkt = HELLXbuild_emote(int(self.uid), int(_tid), _eid, self.key, self.iv)
                            self.writer.write(pkt); await self.writer.drain()
                            await self._send_chat_message(
                                "[27EBF5]EvO dAncE SenT ,\n[A627F5]iF noT sEIng , chEck EmOtEs AlL dOWNloaded .")
                    except Exception:
                        await self._send_chat_message("[F52727]AN erR , TrY aGaIn , If sTiLL cOntaCt owner .")
                asyncio.create_task(_do_dance())
            elif cmd == "!evo_list":
                await self._send_chat_message(
                    "[5427F5]» EVO EmOtEs «\n"
                    "[F227F5]scarlet => 909039011\n"
                    "[F227F5]tiger , woodpecker => 909042008\n"
                    "[F227F5]dreamland , m60 => 909051003\n"
                    "[F227F5]xm8 => 909000085\n"
                    "[F227F5]devil , famas => 909000090\n"
                    "[F227F5]booyahday , ump => 909000098\n"
                    "[F227F5]m4a1 , m4 => 909033001\n"
                    "[F227F5]mp40 => 909040010\n"
                    "[F227F5]100lvl => 909042007 , throne => 909000014\n"
                    "[F227F5]heart , love => 909000045\n"
                    "[F227F5]laugh , lol => 909000002\n"
                    "[A627F5]!dance {uid} {name or id}"
                )
            elif cmd in ("!3", "!5", "!6"):
                _size = int(cmd[1:])
                if self.voice_region_id:
                    await self._send_chat_message("[F52727]ThE bOt AlrEadY iN teAm !")
                    return
                async def _make_squad(_sz=_size, _sender=sender_uid):
                    try:
                        if not self.writer or self.writer.transport.is_closing():
                            return
                        _region = self.region_prefix
                        _ver = getattr(self, '_current_version', '1.132.9')
                        self.writer.write(HELLXbuild_create_squad(_region, _ver, self.key, self.iv))
                        await self.writer.drain()
                        await asyncio.sleep(0.5)
                        self.writer.write(HELLXbuild_change_squad_size(_sz, self.key, self.iv))
                        await self.writer.drain()
                        await asyncio.sleep(0.5)
                        self.writer.write(HELLXbuild_squad_info_request(int(self.uid), self.key, self.iv))
                        await self.writer.drain()
                        self._pending_squad_target = str(_sender)
                    except Exception:
                        await self._send_chat_message("[F52727]BroO sOmetHING weNt WroNg , if U arE oNtaCt owneR")
                asyncio.create_task(_make_squad())
            elif cmd == "!ghost":
                if len(args) < 2:
                    await self._send_chat_message("[F52727]UsAgE => !ghost {team_code} {message}")
                    return
                _gc = args[0]
                _gm = " ".join(args[1:])
                async def _do_ghost(_code=_gc, _msg=_gm):
                    try:
                        if not self.writer or self.writer.transport.is_closing():
                            return
                        self.writer.write(HELLXbuild_join_sq(int(self.uid), _code, self.key, self.iv))
                        await self.writer.drain()
                        await asyncio.sleep(1.0)
                        self.writer.write(HELLXbuild_leave_team(int(self.uid), self.key, self.iv))
                        await self.writer.drain()
                        await asyncio.sleep(0.3)
                        for _ in range(5):
                            self.writer.write(HELLXbuild_ghost_msg(int(self.uid), int(self.uid), _code, _msg, self.key, self.iv))
                            await self.writer.drain()
                            await asyncio.sleep(0.15)
                        await self._send_chat_message("[27EBF5]gHosts SENt !")
                    except Exception:
                        await self._send_chat_message("[F52727]Smthng WnT wronG !")
                asyncio.create_task(_do_ghost())
        except Exception as e:
            import traceback
            HELLXlog("CHAT", f"Command error [{message[:20]}]: {e} | {traceback.format_exc()[-200:]}")
    async def _show_search_page(self):
        if not self._search_results:
            return
        r = self._search_results[self._search_page]
        closed = "[F52727][kapalı]" if self._search_page == 0 else ""
        msg = (
            f"[27EBF5]\u300e Result {self._search_page + 1}/{len(self._search_results)} \u300f {closed}\n"
            f"[5427F5]{r['title']} [{r.get('duration','?')}]\n"
            f"[A627F5]\u2514 {r['channel']}\n"
            f"[F227F5]!previous | !next | !select {self._search_page + 1}"
        )
        await self._send_chat_message(msg)
    async def _do_search(self, query: str, page: int, offset: int = 0):
        import subprocess, json as _json
        try:
            count = 5
            loop = asyncio.get_event_loop()
            def _run():
                return _yt_dlp_run(
                    _yt_dlp_command() + _yt_dlp_base_args(search=True) + [
                        f"ytsearch{offset + count}:{query}", "--dump-json", "--skip-download"
                    ],
                    timeout=12,
                )
            result = await loop.run_in_executor(None, _run)
            all_results = []
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue
                try:
                    info = _json.loads(line)
                    all_results.append({
                        "title": info.get("title", "Unknown"),
                        "channel": info.get("channel", info.get("uploader", "")),
                        "url": f"https://www.youtube.com/watch?v={info.get('id', '')}",
                        "duration": info.get("duration_string", "?"),
                    })
                except Exception:
                    continue
            new_results = all_results[offset:]
            if not new_results:
                await self._send_chat_message("[F52727]No results found.")
                return
            if offset == 0:
                self._search_results = new_results
            else:
                self._search_results.extend(new_results)
            self._search_page = offset
            lines = ["[27EBF5]\u300e Search Results \u300f"]
            for i, r in enumerate(new_results):
                lines.append(f"[F227F5]{offset+i+1}. [5427F5]{r['title'][:40]}\n[A627F5]\u2514 {r['channel']} [{r['duration']}]")
            lines.append("[27EBF5]!select [num] | !next | !previous")
            await self._send_chat_message("\n".join(lines))
        except Exception as e:
            await self._send_chat_message(f"[F52727]Search failed: {e}")
    async def _search_and_play(self, query: str, index: int, lyrics: bool = False):
        import json as _json
        try:
            loop = asyncio.get_running_loop()
            query = " ".join((query or "").split())
            if not query:
                await self._send_chat_message("[F52727]Empty search query.")
                return

            cache_key = query.casefold()
            now = time.monotonic()
            cached = self._search_cache.get(cache_key)
            info = None
            if cached and cached[0] > now:
                info = dict(cached[1])
                HELLXlog("MUSIC", "search cache hit: %s" % query[:60])
            elif cached:
                self._search_cache.pop(cache_key, None)

            last_err = None
            if not info:
                # One flat ytsearch request is usually enough. Only make the
                # second, broader request when the first query returns nothing.
                attempts = [query, query + " audio"]
                for attempt_index, search_text in enumerate(attempts):
                    search_arg = "ytsearch1:%s" % search_text

                    def _run(sa=search_arg):
                        cmd = _yt_dlp_command() + _yt_dlp_base_args(search=True) + [
                            sa, "--dump-json", "--skip-download",
                        ]
                        return _yt_dlp_run(cmd, timeout=12 if attempt_index == 0 else 9)

                    try:
                        result = await loop.run_in_executor(None, _run)
                    except Exception as error:
                        last_err = str(error)
                        HELLXlog("MUSIC", "search try failed: %s" % last_err[:120])
                        continue

                    if result.returncode != 0:
                        err = (result.stderr or result.stdout or "").strip()
                        last_err = err.splitlines()[-1][:120] if err else "search failed"
                        HELLXlog("MUSIC", "yt-dlp search: %s" % last_err)
                        continue

                    for line in (result.stdout or "").splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            candidate = _json.loads(line)
                        except Exception:
                            continue
                        if candidate.get("is_live"):
                            continue
                        video_id = candidate.get("id") or ""
                        video_url = candidate.get("webpage_url") or ""
                        raw_url = candidate.get("url") or ""
                        if not video_url and isinstance(raw_url, str) and raw_url.startswith(("http://", "https://")):
                            video_url = raw_url
                        if not video_url and video_id:
                            video_url = "https://www.youtube.com/watch?v=%s" % video_id
                        if video_url:
                            info = {
                                "id": video_id,
                                "url": video_url,
                                "title": candidate.get("title") or "Unknown",
                                "channel": candidate.get("channel") or candidate.get("uploader") or "",
                            }
                            # Keep the cache small and short-lived. Do not cache
                            # failed or empty queries.
                            if len(self._search_cache) >= 64:
                                oldest_key = next(iter(self._search_cache))
                                self._search_cache.pop(oldest_key, None)
                            self._search_cache[cache_key] = (time.monotonic() + 300, dict(info))
                            break
                    if info:
                        break

            if not info:
                message = "[F52727]No results found."
                if last_err and "timed out" in last_err.lower():
                    message = "[F52727]Search timed out. Check network."
                elif last_err:
                    message = "[F52727]Search failed: %s" % last_err[:80]
                try:
                    await self._send_chat_message(message)
                except Exception:
                    pass
                return

            url = info.get("url") or info.get("webpage_url")
            self._track_title = info.get("title") or "Unknown"
            self._track_channel = info.get("channel") or ""
            HELLXlog("MUSIC", "found %s" % self._track_title[:60])
            try:
                await self._send_chat_message("[27EBF5]Found: %s\nDownloading..." % self._track_title[:50])
            except Exception:
                pass
            await self._play_yt(url, lyrics=lyrics)
        except Exception as error:
            HELLXlog("MUSIC", "search error: %s" % error)
            message = str(error)
            if "timed out" in message.lower():
                message = "YouTube timed out. Check network."
            elif len(message) > 100:
                message = message[:100]
            try:
                await self._send_chat_message("[F52727]Search failed: %s" % message)
            except Exception:
                pass


    async def _yt_info(self, url: str):
        import subprocess, json as _json
        try:
            result = subprocess.run(
                _yt_dlp_command() + ["--dump-json", "--no-playlist", url],
                capture_output=True, text=True, timeout=15
            )
            info = _json.loads(result.stdout)
            title = info.get("title", "Unknown")
            channel = info.get("channel", info.get("uploader", "Unknown"))
            duration = info.get("duration_string", "?")
            views = info.get("view_count", 0)
            await self._send_chat_message(
                f"[27EBF5]Title: {title}\n"
                f"[5427F5]Channel: {channel}\n"
                f"[A627F5]Duration: {duration} | Views: {views:,}"
            )
        except Exception as e:
            await self._send_chat_message(f"[F52727]Error: {e}")
    async def _play_yt(self, url: str, lyrics: bool = False):
        import subprocess, tempfile as _tmp, os as _os
        self._current_url = url
        self._lyrics_enabled = lyrics
        if self._udp_task and not self._udp_task.done():
            self._udp_task.cancel()
            await asyncio.sleep(0.5)
        if self._lyrics_task and not self._lyrics_task.done():
            self._lyrics_task.cancel()
        if not self._voice_ip or not self._voice_port:
            await self._send_chat_message("[27EBF5]Voice connection is still starting, please wait...")
            deadline = asyncio.get_running_loop().time() + 20.0
            while (not self._voice_ip or not self._voice_port) and asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(0.25)
            if not self._voice_ip or not self._voice_port:
                await self._send_chat_message("[F52727]Voice connection failed or timed out.")
                return
        wav_path = _tmp.mktemp(suffix='.wav')
        ogg_path = _tmp.mktemp(suffix='.opus')
        volume_val = self._volume / 100.0
        def _encode():
            import glob as _glob
            raw_path = _tmp.mktemp()
            ffmpeg_path = _ffmpeg_executable()
            opusenc_path = _opusenc_executable()
            # Download best audio; convert with ffmpeg (more reliable than yt-dlp -x alone)
            cmd = _yt_dlp_command() + _yt_dlp_base_args(search=False) + [
                "-f", "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio[acodec^=opus]/bestaudio/best",
                "--ffmpeg-location", ffmpeg_path,
                "-o", raw_path + ".%(ext)s",
                url,
            ]
            try:
                r = _yt_dlp_run(cmd, timeout=180)
            except Exception as e:
                raise Exception(str(e))
            if r.returncode != 0:
                err = (r.stderr or r.stdout or "").strip()
                cmd2 = _yt_dlp_command() + _yt_dlp_base_args(search=False) + [
                    "-x", "--audio-format", "wav", "--audio-quality", "0",
                    "--ffmpeg-location", ffmpeg_path,
                    "-o", raw_path + ".%(ext)s",
                    url,
                ]
                try:
                    r2 = _yt_dlp_run(cmd2, timeout=180)
                except Exception as e:
                    raise Exception(str(e))
                if r2.returncode != 0:
                    err2 = (r2.stderr or r2.stdout or err or "yt-dlp failed").strip()
                    raise Exception(err2.splitlines()[-1][:160] if err2 else "yt-dlp download failed")
            matches = _glob.glob(raw_path + ".*")
            if not matches:
                raise Exception("yt-dlp produced no output file")
            raw_file = matches[0]
            HELLXlog("VOICE", f"Downloaded: {raw_file} ({_os.path.getsize(raw_file)} bytes)")
            # Keep the server-negotiated bitrate, but encode music (not speech) at
            # Opus' native 48 kHz clock with a 20 ms packet cadence.
            br_k = max(8, min(64, int(self.opus_bitrate // 1000)))
            music_filter = f"volume={volume_val},alimiter=limit=0.95:attack=5:release=50"
            # Prefer ffmpeg libopus; this path is available on Termux/Linux too.
            rr = subprocess.run([
                ffmpeg_path, "-loglevel", "error", "-y",
                "-i", raw_file,
                "-ar", "48000", "-ac", "1",
                "-af", music_filter,
                "-c:a", "libopus", "-b:a", f"{br_k}k",
                "-application", "audio", "-frame_duration", "20",
                "-compression_level", "5", "-vbr", "on",
                ogg_path
            ], capture_output=True, text=True)
            if rr.returncode != 0:
                # Fallback: wav then opusenc (Windows / opus-tools)
                rr2 = subprocess.run([
                    ffmpeg_path, "-loglevel", "error", "-y",
                    "-i", raw_file,
                    "-ar", "48000", "-ac", "1",
                    "-af", music_filter,
                    wav_path
                ], capture_output=True, text=True)
                if rr2.returncode != 0:
                    raise Exception((rr.stderr or rr2.stderr or "ffmpeg convert failed").strip()[:160])
                HELLXlog("VOICE", f"Resampled: {wav_path} ({_os.path.getsize(wav_path)} bytes)")
                if not opusenc_path:
                    raise Exception(
                        "ffmpeg has no libopus and opusenc missing. "
                        "Termux: pkg install ffmpeg | PC: install ffmpeg with opus"
                    )
                rr3 = subprocess.run([
                    opusenc_path,
                    "--music", "--bitrate", str(br_k), "--vbr",
                    "--framesize", "20", "--quiet", wav_path, ogg_path
                ], capture_output=True, text=True)
                if rr3.returncode != 0:
                    raise Exception((rr3.stderr or "opusenc failed").strip()[:160])
                try:
                    _os.unlink(wav_path)
                except Exception:
                    pass
            else:
                HELLXlog("VOICE", f"Encoded via ffmpeg libopus: {ogg_path}")
            try:
                _os.unlink(raw_file)
            except Exception:
                pass
            data = open(ogg_path, 'rb').read()
            HELLXlog("VOICE", f"Encoded: {len(data)} bytes opus")
            try: _os.unlink(wav_path)
            except: pass
            try: _os.unlink(ogg_path)
            except: pass
            return data
        def _fetch_lyrics():
            try:
                import yt_dlp, json as _json, tempfile, os, glob
                temp_dir = tempfile.mkdtemp()
                ydl_opts = {
                    'writesubtitles': True,
                    'writeautomaticsub': True,
                    'subtitleslangs': ['tr', 'en'],
                    'subtitlesformat': 'json3',
                    'skip_download': True,
                    'quiet': True,
                    'outtmpl': os.path.join(temp_dir, '%(id)s.%(ext)s'),
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.extract_info(url, download=True)
                sub_files = glob.glob(os.path.join(temp_dir, "*.json3"))
                if not sub_files:
                    return []
                with open(sub_files[0], "r", encoding="utf-8") as f:
                    raw = _json.load(f)
                result = []
                for event in raw.get('events', []):
                    start = event.get('tStartMs', 0)
                    dur = event.get('dDurationMs', 2000)
                    segs = event.get('segs', [])
                    text = ''.join(s.get('utf8', '') for s in segs).strip()
                    if text and text != '\n':
                        result.append((start, start + dur, text))
                for f in sub_files:
                    try: os.unlink(f)
                    except: pass
                try: os.rmdir(temp_dir)
                except: pass
                return result
            except Exception as e:
                HELLXlog("LYRICS", f"Fetch failed: {e}")
                return []
        loop = asyncio.get_event_loop()
        if lyrics:
            encode_fut = loop.run_in_executor(None, _encode)
            lyrics_fut = loop.run_in_executor(None, _fetch_lyrics)
            try:
                ogg_data = await encode_fut
            except Exception as e:
                await self._send_chat_message(f"[F52727]Download failed: {str(e)[:120]}")
                return
            self._lyrics_data = await lyrics_fut
            if self._lyrics_data:
                await self._send_chat_message(f"[27EBF5]Lyrics loaded ({len(self._lyrics_data)} lines)")
            else:
                await self._send_chat_message("[F52727]No lyrics found, playing without.")
        else:
            try:
                ogg_data = await loop.run_in_executor(None, _encode)
            except Exception as e:
                await self._send_chat_message(f"[F52727]Download failed: {str(e)[:120]}")
                return
            self._lyrics_data = []
        await self._send_chat_message(
            f"[27EBF5]Now Playing\n"
            f"[5427F5]{self._track_title[:45]}\n"
            f"[A627F5]{self._track_channel[:30]}"
        )
        self._current_ogg = ogg_data
        frames_preview = list(_ogg_opus_frames_bytes(ogg_data))
        self._track_total_frames = len(frames_preview)
        self._track_current_frame = 0
        self._udp_task = asyncio.create_task(
            self._run_udp_then_leave(self._voice_ip, self._voice_port, ogg_data, 0)
        )
        if self._progress_task and not self._progress_task.done():
            self._progress_task.cancel()
        self._progress_task = asyncio.create_task(self._auto_progress_loop())
        if lyrics and self._lyrics_data:
            self._lyrics_task = asyncio.create_task(self._lyrics_loop())
    async def _chat_read_loop(self, reader):
        try:
            while True:
                data = await reader.read(16384)
                if not data:
                    HELLXlog("CHAT", "Chat server closed the connection")
                    break
                await self._handle_chat_data(data)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            HELLXlog("CHAT", f"Chat reader error: {error}")
        finally:
            # Do not tear down a newer socket if this is an old reader task.
            if reader is self._chat_reader:
                writer = self._chat_writer
                self._chat_reader = None
                self._chat_writer = None
                self._team_chat_auth_sent = False
                if writer:
                    try:
                        writer.close()
                    except Exception:
                        pass
                self._schedule_chat_reconnect()

    async def _reconnect_chat(self):
        """Restore the game's chat socket and re-authenticate the active squad."""
        async with self._chat_reconnect_lock:
            delay = 1.0
            while True:
                if self._chat_writer_open():
                    return
                if not self.chat_ip or not self.chat_port or not self.token:
                    return
                # The chat socket is tied to the authenticated online session.
                if not self.writer:
                    return
                try:
                    if self.writer.transport.is_closing():
                        return
                except Exception:
                    return

                await asyncio.sleep(delay)
                new_reader = None
                new_writer = None
                try:
                    new_reader, new_writer = await asyncio.wait_for(
                        asyncio.open_connection(self.chat_ip, self.chat_port), timeout=8.0
                    )
                    new_writer.write(
                        HELLXbuild_chat_auth_token(
                            self.uid, self.token, self.timestamp, self.key, self.iv
                        )
                    )
                    await new_writer.drain()
                    if self.voice_region_id:
                        owner = self.team_owner_uid if self.team_owner_uid else int(self.uid)
                        new_writer.write(
                            HELLXbuild_chat_auth(
                                owner, str(self.chat_region_id), self.key, self.iv
                            )
                        )
                        await new_writer.drain()
                        self._team_chat_auth_sent = True
                    else:
                        self._team_chat_auth_sent = False

                    self._chat_reader = new_reader
                    self._chat_writer = new_writer
                    self._chat_buffer.clear()
                    HELLXlog("CHAT", f"Reconnected {self.chat_ip}:{self.chat_port}; auth restored")
                    asyncio.create_task(self._chat_read_loop(new_reader))
                    asyncio.create_task(self._chat_keepalive_loop(new_writer))
                    return
                except asyncio.CancelledError:
                    if new_writer:
                        try:
                            new_writer.close()
                        except Exception:
                            pass
                    raise
                except Exception as error:
                    HELLXlog("CHAT", f"Reconnect attempt failed: {error}")
                    if new_writer:
                        try:
                            new_writer.close()
                        except Exception:
                            pass
                    await asyncio.sleep(min(delay, 10.0))
                    delay = min(delay * 2.0, 10.0)
    async def _handle_chat_data(self, data: bytes):
        self._chat_buffer.extend(data)
        buffer = self._chat_buffer
        pos = 0
        while len(buffer) - pos >= 5:
            length = struct.unpack('>I', buffer[pos+1:pos+5])[0]
            if 0 < length < 200000 and pos + 5 + length <= len(buffer):
                payload = bytes(buffer[pos+5:pos+5+length])
                try:
                    proto_data = HELLXdecode_proto(payload)
                    if proto_data:
                        field5 = proto_data.get('5')
                        if isinstance(field5, dict):
                            sender_uid = str(field5.get('1', ''))
                            message = field5.get('4', '')
                            msg_type = field5.get('3', 0)
                            sender_name = ""
                            f9 = field5.get('9', {})
                            if isinstance(f9, dict):
                                sender_name = str(f9.get('1', ''))
                            if isinstance(message, str) and message.strip() and sender_uid != str(self.uid):
                                HELLXlog("CHAT", f"[{sender_name}|{sender_uid}]: {message}")
                                if str(msg_type) == '2':
                                    asyncio.create_task(self._handle_dm(message.strip(), sender_name, sender_uid))
                                else:
                                    asyncio.create_task(self._handle_command(message.strip(), sender_name, sender_uid))
                        self._scan_for_commands(proto_data)
                except Exception as e:
                    HELLXlog("CHAT", f"Parse error: {e}")
                pos += 5 + length
            else:
                if length <= 0 or length >= 200000:
                    pos += 1
                else:
                    break
        if pos:
            del buffer[:pos]
    def _scan_for_commands(self, obj, depth=0):
        if depth > 5:
            return
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, str) and v.strip().lower() == '/leave':
                    asyncio.create_task(self._leave_team())
                elif isinstance(v, (dict, list)):
                    self._scan_for_commands(v, depth+1)
        elif isinstance(obj, list):
            for item in obj:
                self._scan_for_commands(item, depth+1)
    async def _chat_keepalive_loop(self, writer):
        try:
            while self._chat_writer_open(writer):
                await asyncio.sleep(5)
                writer.write(bytes.fromhex('0201'))
                await writer.drain()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            HELLXlog("CHAT", f"Keepalive lost: {error}")
        finally:
            if writer is self._chat_writer:
                reader = self._chat_reader
                self._chat_writer = None
                self._chat_reader = None
                self._team_chat_auth_sent = False
                if writer:
                    try:
                        writer.close()
                    except Exception:
                        pass
                if reader:
                    try:
                        reader.feed_eof()
                    except Exception:
                        pass
                self._schedule_chat_reconnect()
    async def _send_chat_message(self, message: str):
        if not self._chat_writer:
            HELLXlog("CHAT", "No writer!")
            return
        try:
            import time as _t
            ts = int(_t.time())
            owner = self.team_owner_uid if self.team_owner_uid else int(self.uid)
            pkt = await HELLXbuild_chat_message(int(self.uid), owner, message, ts, self.key, self.iv)
            self._chat_writer.write(pkt)
            await self._chat_writer.drain()
            HELLXlog("CHAT", f"Sent: {message[:60]}")
        except Exception as e:
            import traceback
            HELLXlog("CHAT", f"Send error: {e}")
    async def _voice_ping_loop(self, writer, reader):
        try:
            counter = 0
            while writer and not writer.transport.is_closing():
                await asyncio.sleep(5)
                try:
                    session_id = getattr(self, '_voice_f3', 0x0b)
                    ping_pkt = HELLXbuild_voice_ping(self.uid, self.voice_region_id, self.voice_port, session_id)
                    writer.write(ping_pkt)
                    await writer.drain()
                    counter += 1
                except Exception as e:
                    HELLXlog("VOICE", f"TCP ping error: {e}")
                    break
        except asyncio.CancelledError:
            pass
    async def _auto_progress_loop(self):
        try:
            await asyncio.sleep(15)
            while self._udp_task and not self._udp_task.done():
                if self._track_total_frames > 0:
                    frame = self._track_current_frame
                    total = self._track_total_frames
                    elapsed_s = int(frame * 0.02)
                    total_s = int(total * 0.02)
                    pct = min(frame / total, 1.0)
                    bar_len = 16
                    filled = int(bar_len * pct)
                    bar = "[27EBF5]" + "\u25a0" * filled + "[5427F5]" + "\u25a1" * (bar_len - filled)
                    elapsed_str = f"{elapsed_s//60}:{elapsed_s%60:02d}"
                    total_str = f"{total_s//60}:{total_s%60:02d}"
                    playing = not self._udp_task.done()
                    status = "[27EBF5]\u25b6" if playing else "[F52727]\u23f8"
                    await self._send_chat_message(
                        f"{status} [5427F5]{self._track_title[:38]}\n"
                        f"[A627F5]{self._track_channel[:30]}\n"
                        f"{bar}\n"
                        f"[27EBF5]{elapsed_str} [F227F5]/ [27EBF5]{total_str}  "
                        f"[A627F5]Vol:{self._volume}%"
                    )
                await asyncio.sleep(10)
        except asyncio.CancelledError:
            pass
    async def _lyrics_loop(self):
        try:
            if not self._lyrics_data:
                return
            start_time = asyncio.get_event_loop().time()
            sent_idx = 0
            while self._udp_task and not self._udp_task.done():
                now_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)
                while sent_idx < len(self._lyrics_data):
                    s_ms, e_ms, text = self._lyrics_data[sent_idx]
                    if now_ms >= s_ms:
                        clean = text.replace('\n', ' ').strip()
                        if clean:
                            await self._send_chat_message(f"[27EBF5]\u266a {clean}")
                        sent_idx += 1
                    else:
                        break
                if sent_idx >= len(self._lyrics_data):
                    break
                next_ms = self._lyrics_data[sent_idx][0]
                wait = max(0.05, (next_ms - now_ms) / 1000.0)
                await asyncio.sleep(min(wait, 1.0))
        except asyncio.CancelledError:
            pass
    async def _voice_udp_loop(self, ip: str, port: int, encode_task=None, ogg_data: bytes = None, start_frame: int = 0):
        import socket as _sock
        import struct as _st
        import time as _time
        udp_port = port + 2
        if ogg_data is None and encode_task is not None:
            ogg_data = await encode_task
        if not ogg_data:
            HELLXlog("VOICE", "UDP: No audio data")
            return
        frames = list(_ogg_opus_frames_bytes(ogg_data))
        converted = []
        for f in frames:
            if f[0] == 0x78:
                continue
            if f[0] == 0x4b and len(f) > 2 and f[1] == 0x01:
                converted.append(bytes([0x48]) + f[2:])
            else:
                converted.append(f)
        frames = converted
        HELLXlog("VOICE", f"UDP: Streaming {len(frames)} frames from {start_frame} to {ip}:{udp_port}")
        udp = _sock.socket(_sock.AF_INET, _sock.SOCK_DGRAM)
        # Larger kernel buffers absorb brief Android scheduling/network stalls.
        # These are best-effort: some mobile kernels clamp the requested sizes.
        try:
            udp.setsockopt(_sock.SOL_SOCKET, _sock.SO_SNDBUF, 256 * 1024)
            udp.setsockopt(_sock.SOL_SOCKET, _sock.SO_RCVBUF, 128 * 1024)
        except OSError:
            pass
        magic = b'\x41\x6f'
        import random as _random
        seq = _random.randint(0, 0xFFFF)
        ts = _random.randint(0, 0xFFFFFFFF)
        FRAME_SAMPLES = 0x3c0
        FRAME_DURATION = 0.020
        f3_val = getattr(self, '_voice_f3', 0x13e6)
        FIXED_2 = b'\x00\x00' + f3_val.to_bytes(2, 'big')
        mic_open = b'\x71\x5c\x35\x07\x00\x00\x00\x00\x80\x02\x00\x00\x00\x00' + f3_val.to_bytes(2, 'big')
        udp.setblocking(False)
        loop = asyncio.get_running_loop()
        target = (ip, udp_port)
        udp_rx_count = 0
        udp_send_errors = 0
        pacing_late_count = 0

        async def _udp_receiver():
            nonlocal udp_rx_count
            try:
                while True:
                    packet, address = await loop.sock_recvfrom(udp, 4096)
                    udp_rx_count += 1
                    if udp_rx_count <= 5 or udp_rx_count % 100 == 0:
                        HELLXlog(
                            "VOICE",
                            f"UDP RX: #{udp_rx_count} {len(packet)}B from {address} hex={packet[:32].hex()}"
                        )
            except asyncio.CancelledError:
                pass
            except (ConnectionError, OSError) as e:
                HELLXlog("VOICE", f"UDP receiver stopped: {e}")

        udp_rx_task = asyncio.create_task(_udp_receiver())
        try:
            udp.sendto(mic_open, target)
        except OSError as e:
            HELLXlog("VOICE", f"UDP: Failed to open voice stream: {e}")
        try:
            while True:
                seq_loop = seq
                ts_loop = ts
                loop_start = start_frame if seq_loop == seq else 0
                self._track_current_frame = loop_start
                next_send = loop.time()
                for i in range(loop_start, len(frames)):
                    opus_frame = frames[i]
                    f5_val = getattr(self, '_voice_f5', 0)
                    FIXED_1 = f5_val.to_bytes(4, 'big')
                    header = _st.pack('>2sHI4s4s', magic, seq_loop & 0xFFFF, ts_loop & 0xFFFFFFFF, FIXED_1, FIXED_2)
                    packet = header + opus_frame
                    try:
                        # Most small UDP packets fit immediately in the kernel
                        # buffer. A synchronous non-blocking send avoids one
                        # selector/future round-trip for every 20 ms audio frame.
                        # Fall back to the event loop only when the buffer is full.
                        try:
                            udp.sendto(packet, target)
                        except (BlockingIOError, InterruptedError):
                            await loop.sock_sendto(udp, packet, target)
                    except asyncio.CancelledError:
                        self._stopped_frame = i
                        HELLXlog("VOICE", f"UDP: Stopped at frame {i}")
                        raise
                    except OSError as send_error:
                        udp_send_errors += 1
                        # ENOBUFS is transient on some Android/Wi-Fi stacks; give
                        # the kernel a short chance to drain before dropping a frame.
                        if getattr(send_error, "errno", None) in (105, 55):
                            try:
                                await asyncio.sleep(0.002)
                                await loop.sock_sendto(udp, packet, target)
                            except asyncio.CancelledError:
                                self._stopped_frame = i
                                raise
                            except OSError as retry_error:
                                if udp_send_errors <= 3 or udp_send_errors % 100 == 0:
                                    HELLXlog("VOICE", f"UDP send retry failed #{udp_send_errors}: {retry_error}")
                        elif udp_send_errors <= 3 or udp_send_errors % 100 == 0:
                            HELLXlog("VOICE", f"UDP send error #{udp_send_errors}: {send_error}")
                    if i == loop_start:
                        HELLXlog("VOICE", f"UDP: Streaming started (frame {i})")
                    if i % 500 == 0 and i > loop_start:
                        HELLXlog("VOICE", f"UDP: Frame {i}/{len(frames)}")
                    self._track_current_frame = i
                    seq_loop = (seq_loop + 1) & 0xFFFF
                    ts_loop = (ts_loop + FRAME_SAMPLES) & 0xFFFFFFFF
                    next_send += FRAME_DURATION
                    now = loop.time()
                    if next_send < now:
                        # Do not burst several old packets to catch up after an
                        # Android scheduler/network stall; rebase the next deadline.
                        if now - next_send > 0.005:
                            pacing_late_count += 1
                            if pacing_late_count <= 3 or pacing_late_count % 100 == 0:
                                HELLXlog("VOICE", f"UDP pacing delay #{pacing_late_count}: {(now-next_send)*1000:.1f}ms")
                            next_send = now + FRAME_DURATION
                        else:
                            next_send = now
                    try:
                        await asyncio.sleep(max(0.0, next_send - loop.time()))
                    except asyncio.CancelledError:
                        self._stopped_frame = i
                        HELLXlog("VOICE", f"UDP: Stopped at frame {i}")
                        raise
                seq = seq_loop
                ts = ts_loop
                start_frame = 0
                HELLXlog("VOICE", "UDP: Track finished, restarting...")
        except asyncio.CancelledError:
            HELLXlog("VOICE", "UDP: Stopped (cancelled)")
        except Exception as e:
            HELLXlog("VOICE", f"UDP: FATAL ERROR {type(e).__name__}: {e}")
        finally:
            udp_rx_task.cancel()
            try:
                await udp_rx_task
            except asyncio.CancelledError:
                pass
            udp.close()


    async def _run_udp_then_leave(self, ip, port, ogg_data, start_frame=0):
        try:
            await self._voice_udp_loop(ip, port, ogg_data=ogg_data, start_frame=start_frame)
        finally:
            await self._on_song_finished()

    async def _on_song_finished(self):
        HELLXlog("MUSIC", "song playback task finished")
        if getattr(self, "_manual_stop_requested", False):
            return
        self._track_title = ""
        self._current_url = None
        if getattr(self, "_leave_after_song", True):
            try:
                await self._leave_team()
                HELLXlog("TEAM", "left squad after song")
            except Exception as e:
                HELLXlog("TEAM", "leave after song err: %s" % e)

    async def api_join(self, code):
        code = str(code).strip()
        if self.voice_region_id:
            return {"ok": True, "uid": self.uid, "code": code, "region_id": self.voice_region_id, "note": "already in voice"}
        self._joining = True
        self._join_success = False
        join_pkt = HELLXbuild_join_sq(int(self.uid), code, self.key, self.iv)
        sent = False
        # 1) send on online
        try:
            if self.writer and not self.writer.transport.is_closing():
                self.writer.write(join_pkt)
                await self.writer.drain()
                sent = True
                HELLXlog("TEAM", f"join via online code={code}")
        except Exception as e:
            HELLXlog("TEAM", f"online join err: {e}")
        # 2) also send on chat (Ghost style)
        try:
            if self._chat_writer and not self._chat_writer.transport.is_closing():
                self._chat_writer.write(join_pkt)
                await self._chat_writer.drain()
                sent = True
                HELLXlog("TEAM", f"join via chat code={code}")
        except Exception as e:
            HELLXlog("TEAM", f"chat join err: {e}")
        if not sent:
            self._joining = False
            return {"ok": False, "error": "not connected", "uid": self.uid}
        for _ in range(20):
            await asyncio.sleep(0.5)
            if self._join_success or self.voice_region_id:
                break
        self._joining = False
        if self._join_success or self.voice_region_id:
            HELLXlog("TEAM", f"join ok region={self.voice_region_id}")
            return {"ok": True, "uid": self.uid, "code": code, "region_id": self.voice_region_id}
        return {"ok": False, "error": "join failed", "uid": self.uid}

    async def api_play(self, query_or_url):
        if not self.voice_region_id:
            return {"ok": False, "error": "not in voice"}
        q = (query_or_url or "").strip()
        if not q:
            return {"ok": False, "error": "empty query"}
        try:
            if "youtube.com" in q or "youtu.be" in q:
                asyncio.create_task(self._play_yt(q))
                return {"ok": True, "mode": "url", "input": q, "uid": self.uid}
            asyncio.create_task(self._search_and_play(q, 0))
            return {"ok": True, "mode": "search", "input": q, "uid": self.uid}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def api_stop(self):
        stopped = False
        if self._udp_task and not self._udp_task.done():
            self._udp_task.cancel()
            stopped = True
        if getattr(self, "_progress_task", None) and not self._progress_task.done():
            self._progress_task.cancel()
        if getattr(self, "_lyrics_task", None) and not self._lyrics_task.done():
            self._lyrics_task.cancel()
        self._track_title = ""
        self._current_url = None
        return {"ok": True, "stopped": stopped, "uid": self.uid}

    async def api_stop_and_leave(self):
        """Stop playback-related tasks and leave the currently assigned squad."""
        stopped = bool(self._udp_task and not self._udp_task.done())
        current = asyncio.current_task()
        self._manual_stop_requested = True
        tasks = []
        for task in (
            self._udp_task,
            getattr(self, "_progress_task", None),
            getattr(self, "_lyrics_task", None),
        ):
            if task and task is not current and not task.done():
                task.cancel()
                tasks.append(task)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        was_in_team = bool(getattr(self, "voice_region_id", None))
        try:
            if was_in_team:
                await self._leave_team()
            else:
                self._track_title = ""
                self._current_url = None
                self._current_ogg = None
        finally:
            self._manual_stop_requested = False
        self._stopped_frame = 0
        return {
            "ok": True,
            "stopped": stopped,
            "left_team": was_in_team,
            "uid": self.uid,
        }

    def api_status(self):
        playing = bool(self._udp_task and not self._udp_task.done())
        return {
            "uid": self.uid,
            "connected": bool(self.writer and not self.writer.transport.is_closing()),
            "in_voice": bool(self.voice_region_id),
            "region_id": self.voice_region_id,
            "playing": playing,
            "track": self._track_title or None,
            "volume": getattr(self, "_volume", 100),
        }

    async def run(self):
        headers = HELLXdefault_headers("OB55")
        ver_info = await HELLXfetch_version()
        if isinstance(ver_info, (list, tuple)) and len(ver_info) >= 3:
            current_version = ver_info[0] or "1.132.17"
            server_url = ver_info[1] or "https://loginbp.ppmainecoonghj.com/"
            client_ip = ver_info[2] or ""
            release = ver_info[3] if len(ver_info) > 3 else "OB55"
        else:
            current_version, server_url, client_ip, release = "1.132.17", "https://loginbp.ppmainecoonghj.com/", "", "OB55"
        if not server_url:
            server_url = "https://loginbp.ppmainecoonghj.com/"
        headers["ReleaseVersion"] = str(release or "OB55")
        self._current_version = current_version
        city = await HELLXfetch_city(client_ip) if client_ip else "Oran"
        if not city:
            city = "Oran"
        open_id, access_token = await HELLXgenerate_access(self.uid, self.password, "Dalvik/2.1.0 (Linux; U; Android 12; SM-G998B Build/SP1A.210812.016)")
        if not open_id:
            self.login_error = "oauth failed"
            HELLXlog("AUTH", "oauth fail uid=%s" % self.uid)
            return
        major_payload = HELLXbuild_major_login(open_id, access_token, version=current_version, client_ip=client_ip or "10.0.0.1", city=city)
        major_resp = await HELLXmajor_login(major_payload, headers, server_url=server_url, release=release)
        if not major_resp:
            self.login_error = "majorlogin failed"
            HELLXlog("AUTH", "majorlogin fail uid=%s" % self.uid)
            return
        major_proto = HELLXdecode_major_login(major_resp)
        _raw_p = HELLXdecode_proto(major_resp)
        self.token = getattr(major_proto, "token", None) or None
        if isinstance(self.token, bytes):
            self.token = self.token.decode("utf-8", errors="ignore")
        if not self.token:
            t = _raw_p.get("8")
            self.token = t.decode("utf-8", errors="ignore") if isinstance(t, bytes) else t
        self.login_url = getattr(major_proto, "url", None) or None
        if isinstance(self.login_url, bytes):
            self.login_url = self.login_url.decode("utf-8", errors="ignore")
        if not self.login_url:
            u = _raw_p.get("10")
            self.login_url = u.decode("utf-8", errors="ignore") if isinstance(u, bytes) else u
        if not self.login_url:
            self.login_url = server_url
        if not self.token:
            for k, v in (_raw_p or {}).items():
                if isinstance(v, str) and len(v) > 20:
                    self.token = v
                    break
                if isinstance(v, bytes) and len(v) > 20:
                    try:
                        self.token = v.decode("utf-8", errors="ignore")
                        if self.token:
                            break
                    except Exception:
                        pass
        if not self.token:
            self.login_error = "majorlogin missing token"
            HELLXlog("AUTH", "majorlogin missing token body=%s" % (major_resp[:60].hex() if major_resp else "none"))
            return
        proto_ts = getattr(major_proto, "timestamp", None) or _raw_p.get("21")
        try:
            self.timestamp = int(proto_ts) if proto_ts else int(time.time())
        except Exception:
            self.timestamp = int(time.time())
        account_uid = getattr(major_proto, "account_uid", None) or None
        if not account_uid:
            account_uid = _raw_p.get("1")
        # ignore bogus uid like 1 from bad parse
        if account_uid and str(account_uid) not in ("0", "1", "None"):
            self.uid = str(account_uid)
        new_key = getattr(major_proto, "key", b"") or b""
        new_iv = getattr(major_proto, "iv", b"") or b""
        if isinstance(new_key, bytes) and len(new_key) in (16, 24, 32):
            self.key = new_key
        if isinstance(new_iv, bytes) and len(new_iv) == 16:
            self.iv = new_iv
        HELLXlog("AUTH", f"MajorLogin OK uid={self.uid}")
        login_data_resp = await HELLXget_login_data(self.login_url, open_id, access_token, self.token, headers, version=current_version, client_ip=client_ip, city=city, payload=major_payload, release=release)
        if not login_data_resp:
            self.login_error = "getlogindata failed"
            HELLXlog("AUTH", f"getlogindata fail uid={self.uid}")
            return
        self.voice_candidates = []  
        voice_data = HELLXextract_garena_voice_data(login_data_resp)
        for entry in voice_data["idc_servers"]:
            parts = entry['ip_port'].split(':')
            ip, port = parts[0], int(parts[1])
            HELLXlog("VOICE", f"IDC Server => region={entry['region']} idc={entry['idc']} ip_port={entry['ip_port']}")
            if entry['idc'] == 'IDC2':
                self.voice_ip = ip
                self.voice_port = port
                self.voice_candidates.insert(0, (ip, port))
            else:
                self.voice_candidates.append((ip, port))
        if voice_data["webrtc"]:
            w = voice_data["webrtc"]
            HELLXlog("VOICE", f"WebRTC Fallback => domains={w['domains']} ips={w['ips']}")
            sdk_domains = w.get('domains', [])
            if sdk_domains:
                first_domain = sdk_domains[0]
                self._sdk_verify_domain = first_domain
        region_val = _raw_p.get('2') or _raw_p.get('3')
        if region_val and isinstance(region_val, str) and region_val.isalpha():
            self.region_prefix = region_val.upper()
            _region_to_ext = {
                'EUROPE': 'eu', 'VN': 'vn', 'SA': 'sa', 'BR': 'br',
                'ID': 'id', 'TW': 'tw', 'TH': 'th', 'SG': 'sg',
                'ME': 'me', 'IND': 'in', 'NA': 'na', 'LATAM': 'la',
            }
            _region_to_sdk_domain = {
                'EUROPE': 'ff.rtc.grtc.garenanow.com',
                'VN': 'ff.rtc.grtc.garenanow.com',
                'SA': 'ff.rtc.grtc.garenanow.com',
                'BR': 'ff.rtc.grtc.garenanow.com',
                'ID': 'ff.rtc.grtc.garenanow.com',
                'TW': 'ff.rtc.grtc.garenanow.com',
                'TH': 'ff.rtc.grtc.garenanow.com',
                'SG': 'ff.rtc.grtc.garenanow.com',
                'ME': 'ff.rtc.grtc.garenanow.com',
                'IND': 'ff.rtc.grtc.garenanow.com',
            }
            self.ext_region = _region_to_ext.get(self.region_prefix, self.region_prefix.lower()[:2])
            if not voice_data.get("webrtc"):
                self._sdk_verify_domain = _region_to_sdk_domain.get(self.region_prefix, 'ff.rtc.grtc.garenanow.com')
            HELLXlog("AUTH", f"Region prefix: {self.region_prefix} ext: {self.ext_region} sdk_domain: {self._sdk_verify_domain}")
        ld_proto = HELLXdecode_login_data(login_data_resp)
        online_port_str = getattr(ld_proto, 'Online_IP_Port', None) or getattr(ld_proto, 'online_ip_port', None)
        account_port_str = getattr(ld_proto, 'AccountIP_Port', None) or getattr(ld_proto, 'account_ip_port', None)
        if online_port_str and ':' in online_port_str:
            parts = online_port_str.split(":")
            self.online_ip = parts[0]
            self.online_port = int(parts[1])
            HELLXlog("NETWORK", f"Online Server from GetLoginData: {self.online_ip}:{self.online_port}")
        if account_port_str and ':' in account_port_str:
            parts = account_port_str.split(":")
            self.chat_ip = parts[0]
            self.chat_port = int(parts[1])
            HELLXlog("NETWORK", f"Chat Server from GetLoginData: {self.chat_ip}:{self.chat_port}")
        # Chat auth: Ghost CrAuThTK (6d19)
        if self.chat_ip and self.chat_port:
            try:
                cr, cw = await asyncio.wait_for(
                    asyncio.open_connection(self.chat_ip, self.chat_port), timeout=5.0)
                self._chat_reader = cr
                self._chat_writer = cw
                cw.write(HELLXbuild_chat_auth_token(self.uid, self.token, self.timestamp, self.key, self.iv))
                await cw.drain()
                self.login_ok = True
                HELLXlog("CHAT", f"auth ok {self.chat_ip}:{self.chat_port}")
                asyncio.create_task(self._chat_read_loop(cr))
                asyncio.create_task(self._chat_keepalive_loop(cw))
            except Exception as e:
                HELLXlog("CHAT", f"connect fail: {e}")

        # Online auth: Ghost Final Token (830c)
        HELLXlog("NETWORK", f"Connecting Online {self.online_ip}:{self.online_port}")
        online_pkt = HELLXbuild_fnl_token_ghost(self.uid, self.token, self.timestamp, self.key, self.iv)
        try:
            reader, writer = await asyncio.open_connection(self.online_ip, self.online_port)
            writer.write(online_pkt)
            await writer.drain()
            HELLXlog("NETWORK", "Online Connection Established")
        except Exception as e:
            HELLXlog("NETWORK", f"Online connect fail: {e}")
            return
        self.writer = writer
        self._online_ready = True
        self.login_ok = True
        HELLXlog("NETWORK", "Online ready")
        if not self._chat_writer_open():
            HELLXlog("CHAT", "No live chat socket after login; reconnect scheduled")
            self._schedule_chat_reconnect()
        asyncio.create_task(HELLXping_loop(writer, HELLXbuild_ping_packet, self.key, self.iv, region=getattr(self, "region_prefix", "ME")))
        await HELLXread_loop(reader, self._handle_tcp_data, self.key, self.iv)


# ---------------------------------------------------------------------------
# Telegram interface: group restriction, developer tools, and polished replies
# ---------------------------------------------------------------------------
TG_EMOJI = {
    # Telegram custom emoji IDs supplied by the owner.
    "check": ("✅", "5303239451743396488"),
    "wave": ("👋", "5472427507842032538"),
    "eagle": ("🦅", "5442961425146361715"),
    "music": ("🎶", "5305326178784026345"),
    "spark": ("✨", "5305242508526129101"),
    "snow": ("❄️", "5303424362970388996"),
    "paws": ("🐾", "5305322257478882040"),
    "bolt": ("⚡", "5305459936950527191"),
    "fire": ("🔥", "5305567285363117548"),
    "boom": ("💥", "5305372723344611364"),
    "hundred": ("💯", "5303114369410833484"),
    "info": ("❗", "5305305657430284249"),
    "question": ("❓", "5305631301850665208"),
    "top": ("🔝", "5305284165413934506"),
    "tool": ("🔧", "5305606932206231039"),
    "eyes": ("👀", "5305625095622922729"),
    "idea": ("💡", "5305668564986926630"),
    "robot": ("👾", "5305493734048174841"),
    "new": ("🆕", "5305268407178923597"),
    "ghost": ("👻", "5303369713806517554"),
    "diamond": ("💎", "5303478406543875382"),
    "star": ("⭐", "5303482860424961978"),
    "moon": ("🌙", "5305355912842616262"),
    "brain": ("🧠", "5305482343794910704"),
    "dice": ("🎲", "5303091455760310940"),
    "butterfly": ("🦋", "5305320393463076072"),
    "battery": ("🔋", "5303139198616773220"),
    "lock": ("🔒", "5305692122882545639"),
    "bell": ("🔔", "5303212230240671479"),
    "coin": ("🪙", "5303263078358490617"),
    "video": ("🎥", "5303165698564987889"),
    "search": ("🔎", "5305305751919564735"),
    "green": ("🟢", "5303153762850871339"),
    "folder": ("📂", "5303316348837865160"),
    "heart": ("💕", "5303494070289605852"),
    "key": ("🔑", "5303180705180723914"),
    "sync": ("🔄", "5303536616235640580"),
    "developers": ("✅", "5305402491762941367"),
    "developer": ("🥸", "5305647704330771284"),
    "track": ("🎵", "5305362471257674401"),
}


def _tg_emoji(name):
    emoji, emoji_id = TG_EMOJI[name]
    return f'<tg-emoji emoji-id="{emoji_id}">{emoji}</tg-emoji>'


_TG_SANS_BOLD = str.maketrans(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
    "𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇",
)


def _tg_font(text):
    """Use a readable Unicode sans-serif bold face for short UI labels."""
    return str(text).translate(_TG_SANS_BOLD)


_TG_DEVELOPER_VISION = _tg_font("See the developer's vision")


def _telegram_help_text(is_developer=False):
    e = _tg_emoji
    return "\n".join([
        f"{_tg_font('Hi')} {e('wave')}",
        "",
        f"{e('check')} {_tg_font('Bot commands')}",
        f"{e('music')} {_tg_font('Adding a bot within a squad for singing')}",
        f"{e('music')} <code>/song TEAM_CODE</code>",
        "",
        f"{e('developer')} {_TG_DEVELOPER_VISION}",
        f"{e('developers')} <code>/dev</code>",
    ])


def _telegram_start_text(is_developer=False):
    e = _tg_emoji
    return "\n".join([
        f"{_tg_font('Hi')} {e('wave')}",
        _tg_font('Music for your squad. One bot for each team.'),
        "",
        f"{e('music')} <code>/song TEAM_CODE</code>",
        f"{e('idea')} <code>/help</code>  {_tg_font('View bot commands')}",
    ])


def _telegram_dev_text():
    e = _tg_emoji
    first = f"{e('developers')} {_tg_font('Bot developers')}"
    developers = (
        f'<a href="https://t.me/qk_7x">{_tg_font("@qk_7x")}</a> , '
        f'<a href="https://t.me/meropvp">{_tg_font("@meropvp")}</a>'
    )
    return "\n".join([
        first,
        f"{e('developer')} {developers}",
    ])


def _telegram_plain_custom_emoji(text):
    """Replace custom-emoji tags with their Unicode fallback for older clients/API errors."""
    return re.sub(r'<tg-emoji\s+emoji-id="[^"]+">(.*?)</tg-emoji>', r'\1', text, flags=re.DOTALL)


def _telegram_access_level(chat, sender_id, developer_id, allowed_group):
    """Return 'group', 'developer_private', or None; a developer in-group is a normal user."""
    chat_type = str((chat or {}).get("type", ""))
    if chat_type in ("group", "supergroup"):
        username = str((chat or {}).get("username", "")).lstrip("@").lower()
        return "group" if username == str(allowed_group).lstrip("@").lower() else None
    if chat_type == "private" and developer_id and int(sender_id or 0) == int(developer_id):
        return "developer_private"
    return None


def _telegram_parse_command(message):
    raw = (message.get("text") or message.get("caption") or "").strip()
    if not raw or not raw.startswith("/"):
        return "", []
    parts = raw.split()
    command = parts[0][1:].split("@", 1)[0].lower()
    return command, parts[1:]


def _telegram_video_file_id(message):
    if not isinstance(message, dict):
        return None
    video = message.get("video")
    if isinstance(video, dict) and video.get("file_id"):
        return video["file_id"]
    document = message.get("document")
    if (isinstance(document, dict)
            and str(document.get("mime_type", "")).startswith("video/")
            and document.get("file_id")):
        return document["file_id"]
    return None


def _telegram_writer_open(writer):
    if writer is None:
        return False
    try:
        return not writer.is_closing()
    except Exception:
        try:
            return not writer.transport.is_closing()
        except Exception:
            return False


def _telegram_idle_sessions(active_bots, start_index=0):
    """Return available sessions in round-robin order; never include a busy squad session."""
    bots = list(active_bots or [])
    if not bots:
        return []
    start = int(start_index or 0) % len(bots)
    ordered = bots[start:] + bots[:start]
    return [
        bot for bot in ordered
        if not getattr(bot, "voice_region_id", None)
        and _telegram_writer_open(getattr(bot, "writer", None))
        and _telegram_writer_open(getattr(bot, "_chat_writer", None))
    ]


async def run_telegram_bot(token: str, active_bots: list, config: dict, config_path: str):
    import aiohttp
    import asyncio
    import html
    import json
    import os
    import re

    offset = 0
    song_lock = asyncio.Lock()
    next_session_index = 0
    base_url = f"https://api.telegram.org/bot{token}"
    developer_id = int(config.get("developer_id", 0) or 0)
    allowed_group = str(config.get("allowed_group_username", "loginbplike")).lstrip("@").lower()

    def save_config():
        temp_path = config_path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(config, handle, indent=4, ensure_ascii=False)
            handle.write("\n")
        os.replace(temp_path, config_path)

    async def telegram_api(method, payload):
        try:
            async with session.post(f"{base_url}/{method}", json=payload, timeout=25) as response:
                result = await response.json(content_type=None)
                if response.status == 200 and result.get("ok"):
                    return result.get("result")
                HELLXlog("TELEGRAM", f"{method} failed: {result.get('description', response.status)}")
        except Exception as error:
            HELLXlog("TELEGRAM", f"{method} error: {error}")
        return None

    async def configure_command_menus():
        # Remove broad/global command menus first. Only the official group and
        # the developer's private chat receive a menu afterwards.
        for scope in (
            {"type": "default"},
            {"type": "all_private_chats"},
            {"type": "all_group_chats"},
        ):
            await telegram_api("deleteMyCommands", {"scope": scope})

        user_commands = [
            {"command": "start", "description": "Open the welcome screen"},
            {"command": "help", "description": "View commands and instructions"},
            {"command": "song", "description": "Connect one bot to a team"},
            {"command": "dev", "description": "View bot developers"},
        ]
        developer_commands = user_commands + [
            {"command": "admin", "description": "Open developer controls"},
            {"command": "status", "description": "View session status"},
            {"command": "sethelpvideo", "description": "Set the Help video"},
            {"command": "setsongvideo", "description": "Set the result video"},
            {"command": "delhelpvideo", "description": "Remove the Help video"},
            {"command": "delsongvideo", "description": "Remove the result video"},
        ]
        await telegram_api("setMyCommands", {
            "commands": user_commands,
            "scope": {"type": "chat", "chat_id": f"@{allowed_group}"},
        })
        await telegram_api("setMyCommands", {
            "commands": developer_commands,
            "scope": {"type": "chat", "chat_id": developer_id},
        })

    async def send_text(session, chat_id, text, reply_to_message_id=None):
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_to_message_id:
            payload["reply_to_message_id"] = int(reply_to_message_id)
            payload["allow_sending_without_reply"] = True
        try:
            async with session.post(f"{base_url}/sendMessage", json=payload, timeout=25) as response:
                result = await response.json(content_type=None)
                if response.status == 200 and result.get("ok"):
                    return True
                description = str(result.get("description", response.status))
                HELLXlog("TELEGRAM", f"sendMessage failed: {description}")
                # If a custom emoji entity is unsupported, retry with its Unicode emoji.
                lower_description = description.lower()
                if "emoji" in lower_description or "entity" in lower_description or "parse" in lower_description or "unsupported start tag" in lower_description:
                    fallback = dict(payload)
                    fallback["text"] = _telegram_plain_custom_emoji(text)
                    async with session.post(f"{base_url}/sendMessage", json=fallback, timeout=25) as retry:
                        retry_result = await retry.json(content_type=None)
                        if retry.status == 200 and retry_result.get("ok"):
                            return True
                        HELLXlog("TELEGRAM", f"sendMessage fallback failed: {retry_result.get('description', retry.status)}")
                return False
        except Exception as error:
            HELLXlog("TELEGRAM", f"sendMessage error: {error}")
            return False

    async def send_content(session, chat_id, text, video_key=None, reply_to_message_id=None):
        video_id = config.get(video_key, "") if video_key else ""
        if video_id:
            payload = {
                "chat_id": chat_id,
                "video": video_id,
                "caption": text,
                "parse_mode": "HTML",
                "supports_streaming": True,
            }
            if reply_to_message_id:
                payload["reply_to_message_id"] = int(reply_to_message_id)
                payload["allow_sending_without_reply"] = True
            try:
                async with session.post(f"{base_url}/sendVideo", json=payload, timeout=45) as response:
                    result = await response.json(content_type=None)
                    if response.status == 200 and result.get("ok"):
                        return True
                    HELLXlog("TELEGRAM", f"sendVideo failed; using text fallback: {result.get('description', response.status)}")
            except Exception as error:
                HELLXlog("TELEGRAM", f"sendVideo error; using text fallback: {error}")
        return await send_text(session, chat_id, text, reply_to_message_id)

    async def handle_song(session, chat_id, code, reply_to_message_id=None):
        nonlocal next_session_index
        if not re.fullmatch(r"[A-Za-z0-9_-]{4,32}", code):
            await send_text(
                session,
                chat_id,
                f"{_tg_emoji('question')} {_tg_font('Invalid team code')}\n{_tg_font('Use:')} <code>/song TEAM_CODE</code>",
                reply_to_message_id=reply_to_message_id,
            )
            return

        # Serialize allocations so two Telegram requests cannot reserve the same session.
        async with song_lock:
            existing = next((
                bot for bot in active_bots
                if getattr(bot, "_telegram_team_code", None) == code
                and getattr(bot, "voice_region_id", None)
            ), None)
            if existing is not None:
                text = "\n".join([
                    f"{_tg_emoji('check')} {_tg_font('Done')}",
                    f"{_tg_emoji('music')} {_tg_font('A bot was introduced into the team')}",
                    f"{_tg_emoji('dice')} {_tg_font('TEAM')}  {html.escape(code)}",
                    f"{_tg_emoji('battery')} {_tg_font('TEAM CONNECTED')}",
                    f"{_tg_emoji('spark')} {_tg_font('ACCOUNT')}  {html.escape(str(existing.uid))}",
                    f"{_tg_emoji('track')} {_tg_font('ACCOUNTS JOINED')}  1",
                ])
                await send_content(session, chat_id, text, "song_video_file_id", reply_to_message_id=reply_to_message_id)
                return

            candidates = _telegram_idle_sessions(active_bots, next_session_index)
            if not candidates:
                text = "\n".join([
                    f"{_tg_emoji('eagle')} {_tg_font('Team connection')}",
                    "",
                    f"{_tg_emoji('dice')} {_tg_font('TEAM')}  <code>{html.escape(code)}</code>",
                    f"{_tg_emoji('battery')} {_tg_font('No available session')}",
                     _tg_font("All logged-in accounts are already in a team or their game/chat connection is offline."),
                ])
                await send_content(session, chat_id, text, "song_video_file_id", reply_to_message_id=reply_to_message_id)
                return

            # Exactly one bot receives this team code. Accounts that are already
            # inside a team were filtered out above; the round-robin cursor advances
            # so the next distinct /song request can use another idle account.
            selected = candidates[0]
            selected_result = None
            attempted = 1
            selected_index = active_bots.index(selected)
            next_session_index = (selected_index + 1) % len(active_bots)
            try:
                selected_result = await selected.api_join(code)
            except Exception as error:
                selected_result = {
                    "ok": False,
                    "uid": getattr(selected, "uid", "unknown"),
                    "error": str(error),
                }

            # A delayed team notification can arrive just after api_join's timeout.
            if not (isinstance(selected_result, dict) and selected_result.get("ok")):
                for _ in range(6):
                    if getattr(selected, "voice_region_id", None):
                        selected_result = {
                            "ok": True,
                            "uid": getattr(selected, "uid", "unknown"),
                            "code": code,
                            "region_id": getattr(selected, "voice_region_id", None),
                            "note": "confirmed after response delay",
                        }
                        break
                    await asyncio.sleep(0.5)

            if isinstance(selected_result, dict) and selected_result.get("ok"):
                selected._telegram_team_code = code
            else:
                detail = str((selected_result or {}).get("error", "join failed"))[:90]
                text = "\n".join([
                    f"{_tg_emoji('music')} {_tg_font('Team connection')}",
                    "",
                    f"{_tg_emoji('dice')} {_tg_font('TEAM')}  <code>{html.escape(code)}</code>",
                    f"{_tg_emoji('question')} {_tg_font('Connection not confirmed')}",
                    f"<i>{html.escape(detail)}</i>",
                     _tg_font("One account was tried. No other account was sent to this team."),
                ])
                await send_content(session, chat_id, text, "song_video_file_id", reply_to_message_id=reply_to_message_id)
                HELLXlog(
                    "TELEGRAM",
                    f"/song code={code}: no confirmed join; one account tried uid={getattr(selected, 'uid', 'unknown')}",
                )
                return

            # Wait briefly for the voice endpoint and squad-chat auth; the command reader
            # is needed for in-game /play messages, while /play itself remains unchanged.
            deadline = asyncio.get_running_loop().time() + 12.0
            while asyncio.get_running_loop().time() < deadline:
                voice_ready = bool(getattr(selected, "_voice_ip", None) and getattr(selected, "_voice_port", None))
                chat_ready = bool(
                    _telegram_writer_open(getattr(selected, "_chat_writer", None))
                    and getattr(selected, "_team_chat_auth_sent", False)
                )
                if voice_ready and chat_ready:
                    break
                await asyncio.sleep(0.25)

            voice_ready = bool(getattr(selected, "_voice_ip", None) and getattr(selected, "_voice_port", None))
            chat_ready = bool(
                _telegram_writer_open(getattr(selected, "_chat_writer", None))
                and getattr(selected, "_team_chat_auth_sent", False)
            )
            result_text = "\n".join([
                f"{_tg_emoji('check')} {_tg_font('Done')}",
                f"{_tg_emoji('music')} {_tg_font('A bot was introduced into the team')}",
                f"{_tg_emoji('dice')} {_tg_font('TEAM')}  {html.escape(code)}",
                f"{_tg_emoji('battery')} {_tg_font('TEAM CONNECTED')}",
                f"{_tg_emoji('spark')} {_tg_font('ACCOUNT')}  {html.escape(str(selected.uid))}",
                f"{_tg_emoji('track')} {_tg_font('ACCOUNTS JOINED')}  1",
            ])
            await send_content(
                session, chat_id, result_text, "song_video_file_id",
                reply_to_message_id=reply_to_message_id,
            )
            HELLXlog(
                "TELEGRAM",
                f"/song code={code}: one account confirmed uid={selected.uid}; tried={attempted}; voice_ready={voice_ready}; chat_ready={chat_ready}",
            )

    HELLXlog(
        "TELEGRAM",
        f"Polling enabled; group=@{allowed_group}; developer_id={'configured' if developer_id else 'NOT CONFIGURED'}",
    )
    timeout = aiohttp.ClientTimeout(total=40)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        await configure_command_menus()
        while True:
            try:
                params = {
                    "offset": offset,
                    "timeout": 30,
                    "allowed_updates": json.dumps(["message"]),
                }
                async with session.get(f"{base_url}/getUpdates", params=params, timeout=35) as response:
                    data = await response.json(content_type=None)
                    if response.status != 200 or not data.get("ok"):
                        HELLXlog("TELEGRAM", f"getUpdates failed: {data.get('description', response.status)}")
                        await asyncio.sleep(4)
                        continue

                for update in data.get("result", []):
                    offset = update.get("update_id", offset) + 1
                    message = update.get("message") or {}
                    chat = message.get("chat") or {}
                    sender = message.get("from") or {}
                    chat_id = chat.get("id")
                    message_id = message.get("message_id")
                    sender_id = int(sender.get("id", 0) or 0)
                    chat_type = chat.get("type", "")
                    chat_username = str(chat.get("username", "")).lstrip("@").lower()
                    access_level = _telegram_access_level(
                        chat, sender_id, developer_id, allowed_group
                    )
                    is_official_group = access_level == "group"
                    is_developer_private = access_level == "developer_private"

                    # The developer has the same public permissions as everyone else in-group.
                    # Private access is reserved exclusively for the configured developer ID.
                    if access_level is None:
                        continue

                    command, args = _telegram_parse_command(message)
                    if not command:
                        continue

                    if command in ("start", "help"):
                        text = _telegram_start_text(is_developer_private) if command == "start" else _telegram_help_text(is_developer_private)
                        await send_content(
                            session, chat_id, text, "help_video_file_id",
                            reply_to_message_id=message_id,
                        )
                        continue

                    if command == "song":
                        if len(args) != 1:
                            await send_text(
                                session,
                                chat_id,
                                f"{_tg_emoji('music')} {_tg_font('Team code required')}\n{_tg_font('Send:')} <code>/song TEAM_CODE</code>",
                                reply_to_message_id=message_id,
                            )
                        else:
                            await handle_song(session, chat_id, args[0], message_id)
                        continue

                    if command == "dev":
                        await send_text(session, chat_id, _telegram_dev_text(), reply_to_message_id=message_id)
                        continue

                    # The following commands are accepted only in the developer's private chat.
                    if not is_developer_private:
                        continue

                    if command == "admin":
                        admin_text = "\n".join([
                            f"{_tg_emoji('diamond')} {_tg_font('Developer panel')}",
                            "",
                            f"{_tg_emoji('video')} <code>/sethelpvideo</code>",
                            f"{_tg_emoji('video')} <code>/setsongvideo</code>",
                            f"{_tg_emoji('folder')} <code>/delhelpvideo</code>",
                            f"{_tg_emoji('folder')} <code>/delsongvideo</code>",
                            f"{_tg_emoji('bell')} <code>/status</code>",
                            "",
                             _tg_font("To set a video, send it with the matching command as caption, or reply to it with the command."),
                        ])
                        await send_text(session, chat_id, admin_text, reply_to_message_id=message_id)
                        continue

                    if command == "status":
                        connected = sum(
                            1 for bot in active_bots
                            if _telegram_writer_open(getattr(bot, "writer", None))
                            or _telegram_writer_open(getattr(bot, "_chat_writer", None))
                        )
                        in_voice = sum(1 for bot in active_bots if getattr(bot, "voice_region_id", None))
                        idle = max(0, connected - in_voice)
                        status_text = "\n".join([
                            f"{_tg_emoji('diamond')} {_tg_font('Session status')}",
                            "",
                            f"{_tg_emoji('folder')} {_tg_font('Loaded accounts')}  <code>{len(active_bots)}</code>",
                            f"{_tg_emoji('green')} {_tg_font('Connected')}  <code>{connected}</code>",
                            f"{_tg_emoji('music')} {_tg_font('In team / voice')}  <code>{in_voice}</code>",
                            f"{_tg_emoji('battery')} {_tg_font('Idle')}  <code>{idle}</code>",
                        ])
                        await send_text(session, chat_id, status_text, reply_to_message_id=message_id)
                        continue

                    if command in ("sethelpvideo", "setsongvideo"):
                        video_id = _telegram_video_file_id(message)
                        if not video_id:
                            video_id = _telegram_video_file_id(message.get("reply_to_message"))
                        if not video_id:
                            await send_text(
                                session,
                                chat_id,
                                f"{_tg_emoji('video')} {_tg_font('Send a video with')} <code>/{command}</code> {_tg_font('as its caption, or reply to a video with')} <code>/{command}</code>.",
                                reply_to_message_id=message_id,
                            )
                            continue
                        key = "help_video_file_id" if command == "sethelpvideo" else "song_video_file_id"
                        config[key] = video_id
                        save_config()
                        target = "Help interface" if key == "help_video_file_id" else "/song result"
                        await send_text(session, chat_id, f"{_tg_emoji('check')} {_tg_font('Video saved')}\n{_tg_font(target + ' video has been updated.')}", reply_to_message_id=message_id)
                        continue

                    if command in ("delhelpvideo", "delsongvideo"):
                        key = "help_video_file_id" if command == "delhelpvideo" else "song_video_file_id"
                        config[key] = ""
                        save_config()
                        await send_text(session, chat_id, f"{_tg_emoji('check')} {_tg_font('Video removed')}\n{_tg_font('The selected video has been removed.')}", reply_to_message_id=message_id)
                        continue

            except asyncio.CancelledError:
                raise
            except Exception as error:
                HELLXlog("TELEGRAM", f"Polling error: {error}")
                await asyncio.sleep(5)

async def _render_health_server():
    """Minimal HTTP health endpoint for Render Web Services."""
    port = int(os.environ.get("PORT", "10000"))

    async def handle(reader, writer):
        try:
            await reader.read(4096)
            body = b"OK"
            writer.write(
                b"HTTP/1.1 200 OK\\r\\n"
                b"Content-Type: text/plain; charset=utf-8\\r\\n"
                b"Content-Length: 2\\r\\n"
                b"Connection: close\\r\\n\\r\\n" + body
            )
            await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    server = await asyncio.start_server(handle, "0.0.0.0", port)
    HELLXlog("SYSTEM", f"Render health server listening on 0.0.0.0:{port}")
    async with server:
        await server.serve_forever()


async def main():
    import json
    import os
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, "config.json")
    if not os.path.exists(config_path):
        default_config = {
            "telegram_token": "REPLACE_WITH_NEW_BOT_TOKEN",
            "developer_id": 8401495212,
            "allowed_group_username": "loginbplike",
            "leave_after_join": False,
            "autoplay_url": "",
            "help_video_file_id": "",
            "song_video_file_id": ""
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=4, ensure_ascii=False)
        HELLXlog("SYSTEM", "Created config.json. Set a new Telegram token before starting.")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config.setdefault("developer_id", 8401495212)
    config.setdefault("allowed_group_username", "loginbplike")
    config.setdefault("help_video_file_id", "")
    config.setdefault("song_video_file_id", "")
    config.setdefault("leave_after_song", False)
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or config.get("telegram_token", "")
    HELLXlog("SYSTEM", "Starting HELLX Voice Chat Bot")
    accounts_path = os.path.join(base_dir, "accs.txt")
    accounts = HELLXload_accounts(accounts_path)
    if not accounts:
        HELLXlog("SYSTEM", "No accounts found in accs.txt. Add one UID:PASSWORD per line.")
        return
    active_bots = []
    leave_after_join = config.get("leave_after_join", False)
    for uid, pwd in accounts:
        bot = HELLXBot(uid, pwd)
        bot._leave_after_join = leave_after_join
        bot._leave_after_song = bool(config.get("leave_after_song", False))
        active_bots.append(bot)
    tasks = [bot.run() for bot in active_bots]
    # Render requires a web service to listen on the assigned PORT.
    tasks.append(_render_health_server())
    if token and token not in ("YOUR_TOKEN_HERE", "REPLACE_WITH_NEW_BOT_TOKEN"):
        tasks.append(run_telegram_bot(token, active_bots, config, config_path))
    else:
        HELLXlog("SYSTEM", "Telegram token not configured. Set a NEW token in config.json or TELEGRAM_BOT_TOKEN.")
    await asyncio.gather(*tasks)
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        HELLXlog("SYSTEM", "Exiting...")
