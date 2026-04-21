# Right now

they are hardcoded
they are not aligned 100% with your docs
they are not explainable to a client

👉 So they’re fine for development, but not for production

## DEVIS PIPELINE

User Input
   ↓
extractor.py
   ↓
extractor_schema.py  (schema validation)
   ↓
normalizer.py
   ↓
normalized_spec
   ├── estimator.py       → global range
   └── selector.py
         ↓
      catalog.py
         ↓
      quote_builder.py    → line-item devis
   ↓
service.py
   ↓
API / PDF output
