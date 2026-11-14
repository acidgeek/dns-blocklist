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
- `pubads.g.doubleclick.net` **ya no se permite**: la captura mostró que varias apps (red social de
  blogs, app de metro, app de ofertas) lo usan para anuncios, y la app de streaming con anuncios
  reproduce desde su propio CDN sin tocarlo. Si un video se atora, la primera prueba es exceptuar
  `pubads.g.doubleclick.net` o `imasdk.googleapis.com`.
- Servidor DNS upstream: **AdGuard DNS non-filtered (id 30)**, para que el filtrado sea solo local y
  nuestras excepciones manden.

### Verificación manual (con la grabación activa, sin filtrado)

- **Chat de la app bancaria**: es LivePerson. `lptag.liveperson.net` lo bloquean StevenBlack (la
  lista por defecto de Pi-hole), AdAway, anudeepND adservers y hostsVN; `lpsnmedia.net`, anudeepND y
  Prigent-Ads. **Causa confirmada de la rotura pasada.** Con `allow.txt` el chat pasa completo.
- **App de farmacia (Flutter)**: API, buscador (empathy.co), imágenes y backend en S3 pasan. Comprueba
  conectividad con `www.google.com` y `www.apple.com` (este último se agregó a `protect-hosts.txt`).
  Solo se bloquea analítica.
- **Streaming con anuncios**: el video y el DRM salen de su CDN propio; no usa `pubads` ni `dai`.
- **Servidor de medios**: se entra por IP de la red local, así que el filtrado DNS no lo afecta.

### Publicación

- Repositorio público creado y primera ejecución de GitHub Actions en verde (pruebas, compilación,
  revisión y publicación). La lista responde en la URL de `raw.githubusercontent.com`.
- Los archivos de asistente y el grafo local se excluyen con `.git/info/exclude` (no se publican).

### Importación en AdGuard y la fuga que faltaba

- Importado con `adguard://apply_settings`: quedaron exactamente 2 filtros DNS (integrado + esta lista,
  442 606 reglas ≈ 6.75 MiB) y el servidor 30 (non-filtered). El túnel salió a `unfiltered.adguard-dns.com`.
- **La prueba con AdGuard encendido mostró que los anuncios seguían cargando.** Causa: modo
  "Túnel dividido". Cada conexión a un dominio bloqueado fallaba por Wi-Fi y iOS la reintentaba por
  celular con el DNS del operador (10.x), fuera del túnel. 26 de 36 consultas por celular eran
  dominios bloqueados. No era la lista ni el modo de bloqueo (DnsLibs 2.10.1 ya responde `0.0.0.0`).
- Se cambió a **"Túnel completo"**. Repetida la prueba con la app de metro: **0 conexiones a dominios
  bloqueados**, desapareció el banner y la app siguió funcionando.
- El ajuste "Asistencia Wi-Fi" no aparece en Configuración con el operador de esta línea (eSIM de un
  operador virtual), así que no se puede desactivar por ahí; el túnel completo lo vuelve innecesario.
