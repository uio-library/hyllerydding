# Hyllerydding

Kjapt-og-gæli script for å hente ut lister over dokumenter i bestemte samlinger
og deres hyllestatus fra Alma Analytics i egnet format for hylleskanneren
P.V. Supa LibAssist.

## Oppsett

- Kopier `config.dist.yml` til `config.yml`, og åpne `config.yml` i ønsket teksteditor.
  Legg inn følgende (det ligger allerede eksempelverdier du kan erstatte):
    - en Alma API-nøkkel fra Ex Libris Developer Network som har lesetilgang til Analytics (som alltid
   er det lurt å ikke bruke en nøkkel med flere tilganger enn det man trenger).
    - samlingskoder for samlingene du vil sjekke
    - sti til mappen du vil at rapportene skal havne i.

## Installasjon

1. Valgfritt: Lag et virtuelt miljø for å isolere avhengigheter:

    virtualenv ENV
    . ENV/bin/activate

2. Installer avhengigheter:

    pip install requests untangle tqdm

3. Kjør:

    python hent_lister.py

