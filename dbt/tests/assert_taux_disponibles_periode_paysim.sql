-- Toutes les devises des filiales doivent avoir un taux chaque jour de la période rejouée,
-- sinon les montants EUR seraient faux (ou les lignes perdues lors des jointures).
select t.date_cours, t.code_devise
from {{ ref('int_taux_change_journalier') }} t
join {{ ref('ref_filiales') }} f on f.code_devise = t.code_devise
where t.date_cours between cast('{{ var("date_debut_paysim") }}' as date)
                       and {{ date_fin_analyse() }}
  and t.taux_eur is null
