# Bilddateien aus ChatGPT direkt nach GitHub übertragen

**Anwendungsfall:** Ein Bild wurde in ChatGPT erzeugt oder bearbeitet und soll in `cgars/faulmann` als Blog-Cover, Poster oder sonstiges Asset eingecheckt werden.

**Wichtig:** Nicht vorschnell erklären, man könne „nur Textdateien“ nach GitHub schreiben. Die GitHub-Integration unterstützt **Binärdateien** über `create_blob` mit `encoding: "base64"`. Dieser Weg wurde für das Picard-Cover in [PR #71](https://github.com/cgars/faulmann/pull/71) am 3. November 2026 erfolgreich durchgeführt (Commit [36f226c](https://github.com/cgars/faulmann/commit/36f226ce0962ba85792872686cf74569af2e1299)).

## Erprobter Weg

1. **Bilddatei vorbereiten.** Das fertige Bild im Container auffinden, für den Blog nach Bedarf z. B. in WebP umwandeln und die Originaldatei prüfen. Aus der Binärdatei einen Base64-String ohne Header (`data:image/...;base64,`) erzeugen. Die zu übertragende Länge und möglichst die Prüfsumme erfassen.
2. **Daten zu den GitHub-Tools bringen.** Falls der Dateiinhalt der GitHub-Integration nicht direkt zugänglich ist, den Base64-Text vorübergehend als Textdatei über `files__manage_library` (`upload`, `container_path`) in die Library legen, mit `files__read` in mehreren begrenzten Zeilenfenstern lesen und in `functions.exec` wieder zusammensetzen. Für große Dateien Zeilen in gleichmäßige Stücke umbrechen; nach dem Zusammenfügen Zeilenumbrüche entfernen. Länge/Vollständigkeit prüfen. Den Base64-String **nicht** in die sichtbare Antwort kopieren.
3. **Git-Blob erzeugen.** `mcp__GitHub__create_blob({ repository_full_name: "cgars/faulmann", encoding: "base64", content: base64Text })`. Die zurückgegebene Blob-SHA merken.
4. **Branch-Stand ermitteln.** Den aktuellen Head des Zielbranches und den dazugehörigen Tree-SHA lesen, bevor Änderungen ausgeführt werden. Nicht blind mit alten SHAs arbeiten.
5. **Bild und Post zusammenführen.** Mit `mcp__GitHub__create_tree` unter Angabe von `base_tree_sha` einen neuen Tree erzeugen. Für das Bild einen Tree-Eintrag `{ path, mode: "100644", type: "blob", sha: imageBlobSha }` verwenden. Für die Markdown-Datei einen weiteren Tree-Eintrag `{ path, mode: "100644", type: "blob", content: updatedMarkdown }` ergänzen. So landen Bild und Einbindung in **einem Commit**.
6. **Commit und Branch aktualisieren.** `mcp__GitHub__create_commit({ repository_full_name, message, tree_sha, parent_sha: previousHead })` und danach `mcp__GitHub__update_ref({ repository_full_name, branch_name, sha: newCommit, expected_sha: previousHead })`. Mit `expected_sha` einen stillen Überschreibkonflikt vermeiden.
7. **Verifizieren.** PR und Markdown-Datei vom aktualisierten Branch erneut abrufen, den Bildpfad im Text prüfen und wenn möglich auch die neue Bilddatei über GitHub-Objektmetadaten oder ein Browser-Preview kontrollieren. Die temporäre Library-Transferdatei anschließend löschen.

## Typisches Jekyll-Muster

Bildpfad:

```text
assets/img/posts/<post-slug>/cover.webp
```

Im Blogpost, direkt nach dem YAML-Frontmatter:

```markdown
![Sinnvolle Bildbeschreibung](/assets/img/posts/<post-slug>/cover.webp)
```

Bei noch unfertigen Texten `published: false` beibehalten und den Pull Request als Draft öffnen bzw. belassen.

## Fehler, die wir nicht wiederholen wollen

- **Nicht:** Behaupten, GitHub könne hier nur UTF-8-Text annehmen. Das gilt für `create_file`, **nicht** für `create_blob` mit Base64.
- **Nicht:** Ein lokales `/mnt/data`-Verzeichnis mit dem GitHub-Repo verwechseln. Die Containerdatei muss über die passende API transportiert werden.
- **Nicht:** Die Base64-Daten sichtbar ausgeben oder bei der Übertragung kürzen. Bei großen Dateien stückweise lesen und vollständig zusammenfügen.
- **Nicht:** Bestehende Branches durch blindes Verschieben des Refs überschreiben. `expected_sha` verwenden.
- **Nicht:** Das Bild committen, ohne die Markdown-Einbindung zu aktualisieren.
- **Nicht:** Einen bereits angelegten Entwurfs-PR ungefragt mergen oder den Beitrag vorzeitig veröffentlichen.

**Merksatz:** Erst `base64` → GitHub-Blob, dann Tree → Commit → Branch-Ref → Verifikation. Bei getrennter Container- und Connector-Umgebung hilft eine temporäre Textdatei als Transportbrücke.
