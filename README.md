# dns-blocklist

Lista DNS para **AdGuard para iOS** que bloquea anuncios dentro de las apps y telemetría, sin romper bancos, chats de soporte, pagos ni verificación de identidad.

Se reconstruye **cada día** con GitHub Actions a partir de:

| Fuente | Para qué |
|---|---|
| Lista propia de SDKs de anuncios móviles (`lists/block-mobile-ads.txt`) | AdMob, AppLovin, Unity, ironSource, Mintegral, Pangle, Vungle, InMobi… |
| HaGeZi Multi PRO + rastreadores nativos de Apple | anuncios, rastreo y telemetría con pocos falsos positivos |
| AdGuard Mobile Ads filter | dominios de anuncios en apps |
| Listas de la comunidad Pi-hole: StevenBlack (la de Pi-hole por defecto) y las "ticked" de Firebog | anuncios, rastreo, malware, phishing |

## Por qué una sola lista con tope

AdGuard para iOS filtra DNS dentro de una extensión con un presupuesto fijo de **8 MiB para todos los filtros DNS juntos** (DnsLibs, `FILTER_PARAMS_MEM_LIMIT_BYTES`). Cada dominio cuesta ~16 bytes, y lo que no cabe **se descarta en silencio**. Apilar listas de Pi-hole hace justo eso.

Esta lista es **complementaria al filtro DNS que AdGuard ya trae** (`filter_1_ios.txt`): no repite ninguno de sus dominios, y entre las dos quedan en ~7 MiB.

## Cómo evita romper apps

- Nunca bloquea un sufijo público completo (`com.mx`, `github.io`, `cloudfront.net`…), aunque una lista lo traiga.
- `lists/allow.txt`: excepciones para chats de soporte (LivePerson, Glia, Zendesk…), antifraude y biometría (ThreatMetrix, BioCatch, Ravelin…), KYC (Incode, Jumio, MetaMap…), push, configuración remota, enlaces de correo y de ofertas, y streaming. Las excepciones también anulan bloqueos del filtro integrado de AdGuard.
- `lists/protect-hosts.txt`: si una actualización bloquea uno de estos hosts, se crea la excepción sola y se reporta en `dist/stats.json`.
- La compilación **no publica** si una fuente principal falla, si la lista se reduce más de 40 % o si queda algún host protegido bloqueado. En ese caso se mantiene la versión anterior.

## Suscribirse en AdGuard (iOS)

Protección DNS → Filtrado DNS → Filtros DNS → Añadir filtro →

```
https://raw.githubusercontent.com/acidgeek/dns-blocklist/main/dist/adguard-dns.txt
```

Deja activado también el "AdGuard DNS filter" integrado.

## Si algo deja de funcionar

1. En AdGuard → Actividad, busca la app y el dominio bloqueado.
2. Agrégalo a `lists/allow.txt` (`@@||dominio^` incluye subdominios, `@@|host^` es exacto) o a `lists/protect-hosts.txt`.
3. Al hacer push, la lista se regenera sola.

## Desarrollo

```sh
python3 -m unittest discover -s tests   # pruebas sin red
python3 scripts/build.py                # genera dist/adguard-dns.txt y dist/stats.json
```
