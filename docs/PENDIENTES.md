# Pendientes

Marca con `[x]` lo terminado y anota la fecha. Lo más urgente arriba.

## Para dejarlo funcionando

- [ ] **Publicar el repositorio** en GitHub (`acidgeek/dns-blocklist`, público: AdGuard necesita
      descargar la lista sin credenciales) y confirmar que el primer GitHub Actions termina en verde.
- [ ] **Importar en AdGuard** con el enlace que imprime `python3 tools/adguard_import_link.py`: filtro integrado + esta lista
      + servidor 30 (non-filtered). Confirmar en la pantalla de importación.
- [ ] En AdGuard → Protección DNS: verificar que **Implementación DNS = AdGuard** (no "Nativa"; la
      nativa no aplica filtros locales).
- [ ] En AdGuard → Filtros DNS: **desactivar otras listas grandes** que hubiera (cada una suma al tope
      de 8 MiB y si se pasa, se pierden reglas en silencio). Dejar solo el filtro integrado y esta.
- [ ] **VPN del servidor de medios**: desactivar su "VPN On Demand" y crear los Atajos (detalles en `private/CONTEXTO.md`):
  - [ ] Automatización "Al abrir la app de streaming del servidor → Conectar esa VPN".
  - [ ] Automatización "Al cerrarla → Conectar VPN de AdGuard".
  - [ ] Reemplazar el acceso web del servidor de medios por un Atajo: Conectar esa VPN → Mostrar
        página web (URL del servidor) → Conectar VPN de AdGuard (al cerrar la página, AdGuard vuelve).
- [ ] Otra app de VPN gratuita instalada: también desplaza a AdGuard y muestra anuncios propios;
      considerar desinstalarla.

## Verificación

- [ ] Pruebas manuales con captura: chat de la app bancaria, app de farmacia (carrito/compra), acceso
      al servidor de medios, apps con más anuncios, **reproducir video** en la app de streaming con
      anuncios (para decidir `pubads`).
- [ ] **Decidir `pubads.g.doubleclick.net`**: si la app de streaming no lo usa para reproducir,
      quitarlo de `allow.txt` (hoy deja pasar anuncios en varias apps).
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
