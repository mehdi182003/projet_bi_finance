-- Dimension FILIALE : le contexte « qui / où » de chaque filiale (identité, pays, région, devise,
-- système bancaire source, fuseau horaire, source des dépôts réels).
-- RG-MOD-01 : une dimension ne porte AUCUNE mesure. Les nombres propres à chaque filiale (part de
-- marché, taux de réserve cible, nombre de clients, encours et réserve de départ) sont dans la table
-- de faits fct_situation_initiale_filiale ; ils ne doivent jamais être additionnés depuis ici.
select
    f.code_filiale,
    f.nom_filiale,
    f.pays,
    f.code_pays_iso,
    f.region,
    f.code_devise,
    d.libelle_devise,
    d.regime_change,
    f.systeme_source,
    f.fuseau_horaire,
    f.source_depots,
    f.profil_paie,
    f.ordre_affichage
from {{ ref('ref_filiales') }} f
join {{ ref('ref_devises') }} d on d.code_devise = f.code_devise
