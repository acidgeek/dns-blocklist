# Pendientes

Marca con `[x]` lo terminado y anota la fecha. Lo más urgente arriba.

## Para dejarlo funcionando

- [x] (2026-11-13) **Publicar el repositorio** en GitHub (`acidgeek/dns-blocklist`, público: AdGuard necesita
      descargar la lista sin credenciales) y confirmar que el primer GitHub Actions termina en verde.
- [x] (2026-11-13) **Importar en AdGuard** con el enlace que imprime `python3 tools/adguard_import_link.py`: filtro integrado + esta lista
      + servidor 30 (non-filtered). Confirmar en la pantalla de importación.
- [x] (2026-11-13) En AdGuard → Protección DNS: verificar que **Implementación DNS = AdGuard** (no "Nativa"; la
      nativa no aplica filtros locales).
- [x] (2026-11-13) En AdGuard → Filtros DNS: **desactivar otras listas grandes** que hubiera (cada una suma al tope
      de 8 MiB y si se pasa, se pierden reglas en silencio). Dejar solo el filtro integrado y esta.
- [x] (2026-11-13) **VPN del servidor de medios**: su "VPN On Demand" ya estaba apagado; Atajos creados y probados (detalles en `private/CONTEXTO.md`):
  - [x] Automatización "Al abrir la app de streaming del servidor → Conectar esa VPN".
  - [x] Automatización "Al cerrarla → Conectar VPN de AdGuard".
  - [x] Atajo en la pantalla de inicio: Conectar esa VPN → Esperar 2 s → Mostrar
        página web (URL del servidor) → Conectar VPN de AdGuard (al cerrar la página, AdGuard vuelve).
- [ ] Otra app de VPN gratuita instalada (uso ocasional): mientras está activa no hay filtrado (iOS = una
      sola VPN). Al terminar, volver a AdGuard (abrir AdGuard y tocar el interruptor, o Configuración → VPN →
      AdGuard). No usar la "integración" de AdGuard VPN: exige túnel dividido, que se puede eludir.
- [ ] Opcional: mover el atajo del servidor a su carpeta y borrar la app web anterior (esa no cambia la VPN).

- [x] (2026-11-13) AdGuard → **Modo túnel = Túnel completo** (con dividido, iOS esquivaba el filtro por
      la red celular). Si se reinstala AdGuard o se restablece la configuración, **volver a ponerlo**.

## Verificación

- [x] (2026-11-13) Pruebas manuales con captura: chat bancario, farmacia, servidor de medios,
      apps con anuncios, reproducción de video. Resultados en `HISTORIAL.md`.
- [x] (2026-11-13) **`pubads.g.doubleclick.net`**: se quitó de `allow.txt`.
- [ ] Con AdGuard encendido, **reproducir un video** en la app de streaming con anuncios: si se atora,
      exceptuar `imasdk.googleapis.com` (lo bloquea HaGeZi Pro).
- [ ] Volver a grabar con AdGuard **encendido** y confirmar: anuncios bloqueados, ninguna app rota.
- [ ] Revisar AdGuard → Actividad unos días; cualquier bloqueo raro → `allow.txt`.

## Mejoras

- [ ] Brave: Shields en "Agresivo" para anuncios y rastreadores (el DNS ya cubre Brave).
- [ ] Ajustar `max_rules` si se agregan o quitan filtros en AdGuard (mirar
      `estimated_dnslibs_mib_with_reference` en `dist/stats.json`; mantener ≤ 7.2).
- [ ] Rutina semanal opcional en la nube que revise los cambios de las fuentes y abra un PR (ver
      `MANTENIMIENTO.md`).

## Límites conocidos (no se pueden resolver por DNS)

Los anuncios **propios** de Instagram, Facebook, Threads, TikTok, X, Reddit, YouTube, Spotify,
Twitch, Telegram (mensajes patrocinados), Mercado Libre y Amazon salen de los mismos servidores que
el contenido. Bloquearlos por DNS rompería la app. En navegador, Brave Shields sí los quita.
