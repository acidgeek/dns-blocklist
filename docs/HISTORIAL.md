# Historial

Registro de lo que se hizo y por qué, en orden. Lo más nuevo va arriba de cada sesión. Los detalles
personales (qué apps exactamente, dispositivo, red) están en `../private/CONTEXTO.md` (no se publica).

## 2026-11-13 · Sesión 1: diagnóstico y creación del repositorio

**Pedido:** que AdGuard (iOS) vuelva a bloquear anuncios en apps, agregar filtros y bloquear
telemetría, **sin romper apps**. Antes, listas agresivas habían roto el chat de una app bancaria y una
app de farmacia que decía "sin conexión".

### Diagnóstico

1. **AdGuard no estaba filtrando nada.** El túnel de otra VPN estaba activo y el de
   AdGuard no corría. iOS solo permite una VPN; AdGuard no se reactiva solo. Era la causa principal
   de que "volvieran los anuncios".
2. Se leyó el código de AdGuard iOS (`AdguardTeam/AdguardForiOS`, rama `version/v4.5`) y de DnsLibs.
   Hallazgos clave en `MEMORIA.md`: tope de 8 MiB, la importación reemplaza las reglas de usuario,
   el servidor upstream que filtra se salta nuestras excepciones, y las excepciones cubren CNAME.
3. Se grabó el tráfico real del iPhone por USB (`pcapd`), atribuido por proceso, abriendo
   automáticamente 83 apps (~11 s cada una). Resultado: telemetría y SDKs de anuncios por app.

### Lo que se construyó

- `scripts/build.py`: junta HaGeZi Pro, listas Pi-hole (StevenBlack, Firebog ticked), AdGuard Mobile
  Ads y una lista propia de SDKs de anuncios; quita duplicados contra el filtro integrado de AdGuard;
  aplica el tope; protege sufijos públicos; aplica excepciones; tiene compuertas que impiden publicar.
- 13 pruebas sin red (`tests/test_build.py`).
- GitHub Actions diario (`.github/workflows/build.yml`).
- Grafo de conocimiento con graphify (`graphify-out/`, solo local, no se publica).
- Herramientas de verificación en el iPhone (`tools/iphone/`).

### Resultado de la primera compilación

- 251 115 reglas de bloqueo y 151 excepciones; ≈ 6.74 MiB junto con el filtro integrado (tope de 8).
- Se descartaron 98 entradas que eran sufijos públicos (p. ej. `com.cn`, `co.tz`, servicios de DNS
  dinámico enteros) que venían en listas de malware.

### Dominios que la simulación habría roto y se exceptuaron

| Dominio | Qué es | Lo bloqueaba |
|---|---|---|
| `we-stats.com` | BioCatch: biometría de comportamiento antifraude (banca) | HaGeZi / Pi-hole |
| `appdome.com` | Seguridad anti-manipulación de apps (banca) | HaGeZi Pro |
| `ravelin.click` | Antifraude de pagos (`live.ravelin.click`) | **filtro integrado de AdGuard** |
| `acs.m.taobao.com`, `ynuf.aliapp.org`, `umlazada.alibaba.com` | API y seguridad de AliExpress | una lista Pi-hole / HaGeZi |
| `grs.dbankcloud.asia` | Ruteo de servidores de Huawei Health | HaGeZi Pro |
| `cdn.cookielaw.org` y otros CMP | Pantallas de consentimiento (si fallan, apps se atoran) | StevenBlack |
| `matt.mercadolibre.com` / `matt.mercadopago.com` | Atribución de enlaces (enlaces de ofertas) | HaGeZi Pro |
| `cstat.cdn-apple.com` | Lo usa `coreidvd` (identidad en iOS) | HaGeZi Apple |
| `fls-na.amazon.com(.mx)` | Telemetría de Amazon cuyo bloqueo da errores | Pi-hole |

### Decisiones

- Se **confía en HaGeZi Pro** cuando es la que bloquea (p. ej. `tnc0-*.tiktokv.com`, `ocular.*`).
- `pubads.g.doubleclick.net` quedó **permitido provisionalmente** (algunas apps de streaming no
  reproducen sin él), pero la captura mostró que Tumblr, una app de metro y una de ofertas lo usan
  para anuncios. Pendiente decidir con datos de reproducción de video (ver `PENDIENTES.md`).
- Servidor DNS upstream: **AdGuard DNS non-filtered (id 30)**, para que el filtrado sea solo local y
  nuestras excepciones manden.
