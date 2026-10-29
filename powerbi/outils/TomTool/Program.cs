using System;
using System.IO;
using System.Linq;
using Microsoft.AnalysisServices.Tabular;

// Usage : TomTool <model.bim> <dossier_sortie_tmdl>
// 1) charge le modèle TMSL avec la bibliothèque officielle Microsoft (TOM) => valide la structure
// 2) l'écrit au format TMDL (format des projets Power BI .pbip)
// 3) relit le TMDL produit (aller-retour) et affiche un résumé
var bim = File.ReadAllText(args[0]);
var db = JsonSerializer.DeserializeDatabase(bim);
var m = db.Model;
Console.WriteLine($"Modèle chargé : {m.Tables.Count} tables, {m.Tables.Sum(t => t.Measures.Count)} mesures, {m.Relationships.Count} relations, {m.Expressions.Count} paramètres");
if (Directory.Exists(args[1])) Directory.Delete(args[1], true);
TmdlSerializer.SerializeDatabaseToFolder(db, args[1]);
var relu = TmdlSerializer.DeserializeDatabaseFromFolder(args[1]);
Console.WriteLine($"TMDL relu : {relu.Model.Tables.Count} tables, {relu.Model.Tables.Sum(t => t.Measures.Count)} mesures, {relu.Model.Relationships.Count} relations");
foreach (var t in relu.Model.Tables)
    foreach (var c in t.Columns.Where(c => c.Type != ColumnType.RowNumber))
        if (!string.IsNullOrEmpty(c.SortByColumn?.Name) && t.Columns.Find(c.SortByColumn.Name) == null)
            throw new Exception($"sortByColumn introuvable : {t.Name}.{c.Name}");
Console.WriteLine("OK");
