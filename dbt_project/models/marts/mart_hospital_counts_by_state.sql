{{ config(materialized='table') }}

/*
  Simple mart: hospital counts by state from CMS HGI.
  Public aggregate demo — facility-level open data only.
*/

select
    state,
    count(*) as hospital_count
from {{ ref('stg_cms_hospital_general_information') }}
where state is not null
group by 1
order by hospital_count desc, state
