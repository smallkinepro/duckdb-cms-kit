{{ config(materialized='table') }}

/*
  Clean + snake_case CMS Hospital General Information (xubh-q36u).
  Reads bronze Parquet directly. Filters empty facility_id.
  Public facility-level CMS open data — no PHI.
*/

with raw as (
    select *
    from read_parquet('{{ var("bronze_hgi_parquet_relpath") }}')
),

renamed as (
    select
        nullif(trim(cast("Facility ID" as varchar)), '') as facility_id,
        nullif(trim(cast("Facility Name" as varchar)), '') as facility_name,
        nullif(trim(cast("Address" as varchar)), '') as address,
        nullif(trim(cast("City/Town" as varchar)), '') as city_town,
        nullif(trim(cast("State" as varchar)), '') as state,
        nullif(trim(cast("ZIP Code" as varchar)), '') as zip_code,
        nullif(trim(cast("County/Parish" as varchar)), '') as county_parish,
        nullif(trim(cast("Telephone Number" as varchar)), '') as telephone_number,
        nullif(trim(cast("Hospital Type" as varchar)), '') as hospital_type,
        nullif(trim(cast("Hospital Ownership" as varchar)), '') as hospital_ownership,
        nullif(trim(cast("Emergency Services" as varchar)), '') as emergency_services
    from raw
)

select *
from renamed
where facility_id is not null
