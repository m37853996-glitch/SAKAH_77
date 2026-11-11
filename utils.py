import random
import os

def HELLXuser_agent():
    versions = [
        '4.0.18P6', '4.0.19P7', '4.0.20P1', '4.1.0P3', '4.1.5P2', '4.2.1P8',
        '4.2.3P1', '5.0.1B2', '5.0.2P4', '5.1.0P1', '5.2.0B1', '5.2.5P3',
        '5.3.0B1', '5.3.2P2', '5.4.0P1', '5.4.3B2', '5.5.0P1', '5.5.2P3'
    ]
    models = [
        'SM-A125F', 'SM-A225F', 'SM-A325M', 'SM-A515F', 'SM-A725F', 'SM-M215F', 'SM-M325FV',
        'Redmi 9A', 'Redmi 9C', 'POCO M3', 'POCO M4 Pro', 'RMX2185', 'RMX3085',
        'moto g(9) play', 'CPH2239', 'V2027', 'OnePlus Nord', 'ASUS_Z01QD',
    ]
    android_versions = ['9', '10', '11', '12', '13', '14']
    languages = ['en-US', 'es-MX', 'pt-BR', 'id-ID', 'ru-RU', 'hi-IN']
    countries = ['USA', 'MEX', 'BRA', 'IDN', 'RUS', 'IND']
    version = random.choice(versions)
    model = random.choice(models)
    android = random.choice(android_versions)
    lang = random.choice(languages)
    country = random.choice(countries)
    return f"GarenaMSDK/{version}({model};Android {android};{lang};{country};)"


def HELLXdefault_headers(ob_version="OB55"):
    return {
        'User-Agent': 'UnityPlayer/2018.4.12f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)',
        'Connection': "Keep-Alive",
        'Accept-Encoding': "gzip",
        'Content-Type': "application/x-www-form-urlencoded",
        'X-Unity-Version': "2018.4.12f1",
        'X-GA-SV': "1789535859",
        'X-GA': "v1 1",
        'ReleaseVersion': ob_version
    }


def HELLXlog(tag, message):
    print(f"{tag} => {message}", flush=True)


def HELLXload_accounts(filepath):
    """Load account credentials exclusively from a plain-text .txt file.

    Accepted format: one UID:PASSWORD pair per line. Lines beginning with #
    are comments. JSON account stores are deliberately not supported.
    """
    result = []
    if not filepath or not os.path.exists(filepath):
        HELLXlog("ERROR", f"no accounts file: {filepath}")
        return result
    if os.path.splitext(os.fspath(filepath))[1].lower() != ".txt":
        HELLXlog("ERROR", "account source must be accs.txt")
        return result
    try:
        with open(filepath, "r", encoding="utf-8-sig") as handle:
            for line_number, raw_line in enumerate(handle, 1):
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if ":" in line:
                    uid, password = line.split(":", 1)
                elif "," in line:
                    uid, password = line.split(",", 1)
                else:
                    parts = line.split()
                    if len(parts) != 2:
                        HELLXlog("WARN", f"accs.txt line {line_number} ignored: expected UID:PASSWORD")
                        continue
                    uid, password = parts
                uid, password = uid.strip(), password.strip()
                if uid and password:
                    result.append((uid, password))
                else:
                    HELLXlog("WARN", f"accs.txt line {line_number} ignored: empty UID or password")
    except Exception as error:
        HELLXlog("ERROR", f"Failed to load accounts from {filepath} => {error}")
        return []
    if not result:
        HELLXlog("ERROR", "accs.txt contains no valid UID:PASSWORD entries")
    return result
