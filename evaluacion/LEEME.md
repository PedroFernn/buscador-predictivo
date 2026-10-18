# Conjunto de oro

Coloca aquí `oro.csv` (consulta, idioma, doc_id, relevancia) con consultas reales de tu catálogo.
Formato y métricas: `busqueda/evaluacion.py`. Uso: `python -m scripts.calibrar`.

```csv
consulta,idioma,doc_id,relevancia
polvo,es,41,3
polvo,pt,512,3
```

relevancia: 0 (nada) a 3 (exacto). Incluye falsos amigos en ambos idiomas, emojis, abreviaturas y typos.
Hazlo **antes** de tocar el ranking o el motor de búsqueda.
