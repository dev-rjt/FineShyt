# Transaction category boundaries

Every transaction receives exactly one category.

| Category | Included | Excluded or boundary rule |
|---|---|---|
| Fuel | Petrol-station and forecourt fuel purchases | Servicing, tyres and parts go to Automotive |
| Electricity | Named electricity supplier payments | Gas-only payments go to Gas; water/broadband go to Utilities |
| Gas | Named gas supplier payments | Electricity-only payments go to Electricity |
| Public Transport | Rail, bus and urban transit payments | Fuel and vehicle costs are separate |
| Home Improvement | Building materials, hardware and retrofit merchants | General household retail stays Other |
| Automotive | Servicing, tyres, parts and garages | Pump purchases stay Fuel |
| Utilities | Water, broadband, council and mixed utility services | Named electricity and gas payments use their specific category |
| Other | All transactions that do not meet another boundary | Used as the explicit fallback |

High-confidence merchant rules should run first. The transaction classifier handles the remaining descriptions. If the classifier cannot make a reliable distinction, use `OTHER` rather than assigning multiple categories.
