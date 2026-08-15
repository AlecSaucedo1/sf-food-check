# SF Food Check — MVP product specification

## Product promise

A diner should be able to search a San Francisco restaurant and understand its current official health-inspection outcome and recent history in under ten seconds, then drill into the inspector's own narrative when they want context.

## Primary screens

### Search / home
- Restaurant name or address search.
- Filters: All, Pass, Conditional Pass, Closure.
- Latest available inspection date and violation count.
- Five-inspection outcome history indicators.
- List / map-style toggle.

### Nearby
- Uses browser geolocation only after user permission.
- Sorts establishments by distance using coordinates in the inspection record.

### Recent
- Latest inspection per establishment ordered newest first.

### Restaurant profile
- Current official outcome.
- Address, neighborhood, open-in-maps action.
- Count of inspections, passing outcomes, and latest violations.
- Full inspection timeline.
- Inspector narrative with provenance label.
- Corrective action separately identified.
- Violation category, consumer explanation, official finding/code.
- Direct route to official SF inspection lookup and official report URL when available.

## Trust rules

1. No proprietary cleanliness score in MVP.
2. Status colors mirror the conceptual green/yellow/red inspection placard hierarchy without implying endorsement.
3. Inspector comments are never AI-generated.
4. Consumer explanations never replace official descriptions.
5. Demo content is always visibly labeled.
6. If narrative coverage is missing, say so instead of inferring it.
7. Keep raw upstream records for audit/reprocessing.

## MVP success criteria

- Search-to-answer in less than 10 seconds for a known restaurant.
- A user can distinguish current status from historical problems.
- Inspector narrative is readable without hiding official wording.
- Source/provenance is obvious.
- App is usable one-handed on a modern phone.
