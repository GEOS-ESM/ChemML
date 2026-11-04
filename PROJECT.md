{\rtf1\ansi\ansicpg1252\cocoartf2822
\cocoatextscaling0\cocoaplatform0{\fonttbl\f0\fswiss\fcharset0 Helvetica;\f1\fnil\fcharset0 AppleColorEmoji;}
{\colortbl;\red255\green255\blue255;}
{\*\expandedcolortbl;;}
\margl1440\margr1440\vieww37700\viewh24220\viewkind0
\pard\tx720\tx1440\tx2160\tx2880\tx3600\tx4320\tx5040\tx5760\tx6480\tx7200\tx7920\tx8640\pardirnatural\partightenfactor0

\f0\fs24 \cf0 # ChemML Project Development Plan\
\
**Repository**: https://github.com/GEOS-ESM/ChemML.git  \
**Development Branch**: CNPDF_aqforecast_development  \
\
## Project Overview\
\
ChemML is a high-resolution air quality forecasting system that combines satellite observations, numerical model outputs, and ground-based measurements using deep learning. The system is designed to produce probabilistic forecasts of PM2.5, O\uc0\u8323 , and NO\u8322  at fine spatial resolution (e.g., 1 km) over user-defined regions.\
\
### Project Goals\
\
1. **Primary Goal**: Develop an operational air quality forecasting system using machine learning\
2. **Secondary Goals**:\
   - Integrate multiple NASA Earth observation datasets\
   - Provide uncertainty quantification through ensemble forecasting\
   - Enable both retrospective analysis and real-time forecasting\
   - Deploy on NASA NCCS infrastructure\
   - Support scientific research and operational applications\
\
### Target Capabilities\
\
- **Spatial Resolution**: 1 km\
- **Forecast Horizon**: 72 hours (up to 120 hours)\
- **Update Frequency**: Daily\
- **Pollutants**: PM2.5, O\uc0\u8323 , NO\u8322 \
- **Uncertainty**: 90% confidence intervals\
- **Validation**: Comprehensive metrics with cross-validation\
\
## Development Phases\
\
### Phase 1: Foundation - **IN PROGRESS**\
\
**Objective**: Establish project infrastructure and core utilities\
\
**Tasks**:\
- [x] Define project structure\
- [x] Create configuration system design\
- [x] Set up GitHub repository and branch\
- [ ] Implement package structure\
- [ ] Create configuration management system\
- [ ] Implement credentials management\
- [ ] Set up logging utilities\
- [ ] Create database manager framework\
- [ ] Write initial documentation\
\
**Deliverables**:\
- Package skeleton with all directories\
- Configuration file templates\
- Credentials management system\
- Basic logging infrastructure\
- Database manager with incremental update support\
\
**Current Status**: \
- Project objectives and high-level structure defined\
- Ready to begin implementation\
\
**Next Steps**:\
1. Create initial package structure\
2. Implement configuration manager\
3. Implement credentials manager\
4. Create database manager\
\
---\
\
### Phase 2: Data Acquisition - **PLANNED**\
\
**Objective**: Implement data acquisition modules for all sources\
\
**Tasks**:\
- [ ] Implement satellite data acquisition:\
  - [ ] VIIRS MAIAC AOD\
  - [ ] TROPOMI NO\uc0\u8322  and O\u8323 \
  - [ ] PACE NO\uc0\u8322  and O\u8323 \
  - [ ] GOES-ABI AOD\
  - [ ] TEMPO NO\uc0\u8322  and O\u8323  profiles\
- [ ] Implement GEOS-CF model data acquisition\
- [ ] Implement ground station data acquisition:\
  - [ ] EPA AirNow API integration\
  - [ ] OpenAQ API integration\
- [ ] Implement data quality control\
- [ ] Create data download scripts\
- [ ] Test data acquisition on NCCS\
- [ ] Schedule ongoing data ingest\
  - [ ] Create scripts to update database in NCCS on regular (daily) cadence\
  - [ ] Schedule scripts to run automatically using `cron`\
  - [ ] Verify that data are being ingested as intended\
\
**Deliverables**:\
- Functional data acquisition modules for all sources\
- Data quality control procedures\
- Download scripts for historical data\
- Unit tests for data modules\
- Automated database updating script\
- Database integrity verification\
- Documentation for data sources\
\
**Dependencies**:\
- Phase 1 completion\
- NASA Earthdata credentials\
- AirNow and OpenAQ API keys\
- NCCS access\
\
---\
\
### Phase 3: Preprocessing - **PLANNED**\
\
**Objective**: Develop preprocessing pipeline for model inputs\
\
**Tasks**:\
- [ ] Implement ingestion of all data sources into DeepSensor-compatible formats\
- [ ] Create quality control procedures\
- [ ] Implement feature engineering for DeepSensor\
- [ ] Create preprocessing scripts\
- [ ] Optimize for NCCS performance\
\
**Deliverables**:\
- DeepSensor data preparation modules\
- Quality control procedures\
- Feature engineering pipeline\
- Preprocessing scripts\
- Unit tests\
- Documentation\
\
**Dependencies**:\
- Phase 2 completion\
- Sample data from all sources\
\
---\
\
### Phase 4: Forecasting Model - **PLANNED**\
\
**Objective**: Implement DeepSensor-based forecasting system\
\
**Tasks**:\
- [ ] Create DeepSensor wrapper for ConvNP\
- [ ] Implement training pipeline\
- [ ] Implement cross-validation framework\
- [ ] Create DeepSensor forecasting system\
- [ ] Implement inference pipeline\
- [ ] Optimize for GPU training on NCCS\
- [ ] Create model training scripts\
- [ ] Develop model versioning system\
\
**Deliverables**:\
- DeepSensor wrapper module\
- Training pipeline with cross-validation\
- Ensemble forecasting implementation\
- Inference pipeline for 72-hour forecasts\
- Training scripts for NCCS\
- Model checkpointing and versioning\
- Unit tests\
- Documentation\
\
**Dependencies**:\
- Phase 3 completion\
- Preprocessed training data\
- NCCS GPU access\
\
---\
\
### Phase 5: Validation - **PLANNED**\
\
**Objective**: Implement comprehensive validation framework\
\
**Tasks**:\
- [ ] Implement core metrics (bias, RMSE, correlation)\
- [ ] Create stratification framework:\
  - [ ] By monitoring site\
  - [ ] By forecast lead time\
  - [ ] By hour of day\
  - [ ] By region\
- [ ] Implement confidence interval coverage analysis\
- [ ] Create sensitivity analysis for data outages\
- [ ] Implement visualization tools\
- [ ] Create validation reporting system\
- [ ] Develop validation scripts\
\
**Deliverables**:\
- Validation metrics module\
- Stratification framework\
- Sensitivity analysis tools\
- Visualization functions\
- Automated reporting system\
- Validation scripts\
- Unit tests\
- Documentation\
\
**Dependencies**:\
- Phase 4 completion\
- Forecast outputs\
- Ground truth data\
\
---\
\
### Phase 6: Orchestration - **PLANNED**\
\
**Objective**: Implement workflow orchestration for operations\
\
**Tasks**:\
- [ ] Create retrospective mode workflow\
- [ ] Implement real-time mode workflow\
- [ ] Develop scheduling system for daily updates\
- [ ] Create NCCS job submission scripts\
- [ ] Implement automated validation of previous forecasts\
- [ ] Set up monitoring and alerting\
- [ ] Create operational documentation\
- [ ] Test end-to-end workflows\
\
**Deliverables**:\
- Retrospective workflow implementation\
- Real-time workflow with scheduling\
- NCCS deployment scripts\
- Automated validation workflow\
- Monitoring system\
- Operational documentation\
- Integration tests\
\
**Dependencies**:\
- Phases 1-5 completion\
- NCCS production environment setup\
\
---\
\
### Phase 7: Documentation & Testing - **PLANNED**\
\
**Objective**: Complete documentation and comprehensive testing\
\
**Tasks**:\
- [ ] Write comprehensive user guide\
- [ ] Create API reference documentation\
- [ ] Develop example Jupyter notebooks\
- [ ] Write NCCS deployment guide\
- [ ] Complete unit test coverage\
- [ ] Perform integration testing\
- [ ] Conduct security review\
- [ ] Create tutorial videos/materials\
- [ ] Prepare for initial release\
\
**Deliverables**:\
- Complete documentation suite\
- Example notebooks for all workflows\
- Full test coverage\
- Security audit report\
- NCCS deployment guide\
- Tutorial materials\
- Version 0.1.0 release\
\
**Dependencies**:\
- Phases 1-6 completion\
\
---\
\
## Current Development Status\
\
### Completed Items\
- 
\f1 \uc0\u9989 
\f0  Project structure design\
- 
\f1 \uc0\u9989 
\f0  Development roadmap\
\pard\tx720\tx1440\tx2160\tx2880\tx3600\tx4320\tx5040\tx5760\tx6480\tx7200\tx7920\tx8640\pardirnatural\partightenfactor0
\cf0 - 
\f1 \uc0\u9989 
\f0  GitHub repository setup\
\pard\tx720\tx1440\tx2160\tx2880\tx3600\tx4320\tx5040\tx5760\tx6480\tx7200\tx7920\tx8640\pardirnatural\partightenfactor0
\cf0 \
### In Progress\
- 
\f1 \uc0\u55357 \u56580 
\f0  Initial package implementation\
\
### Upcoming\
\pard\tx720\tx1440\tx2160\tx2880\tx3600\tx4320\tx5040\tx5760\tx6480\tx7200\tx7920\tx8640\pardirnatural\partightenfactor0
\cf0 - Configuration manager\
- Credentials manager\
\pard\tx720\tx1440\tx2160\tx2880\tx3600\tx4320\tx5040\tx5760\tx6480\tx7200\tx7920\tx8640\pardirnatural\partightenfactor0
\cf0 - Database manager\
- Unit test framework setup\
- data acquisition modules\
\
## Technical Decisions\
\
### Architecture Decisions\
\
1. **Database Organization**: Monthly NetCDF or CSV files organized by region and data source\
   - Rationale: Balances file size, access speed, and incremental updates\
   \
2. **Machine Learning Framework**: DeepSensor with ConvNP architecture\
   - Rationale: Designed for spatiotemporal data fusion with uncertainty quantification\
   \
3. **Spatial Resolution**: 1 km grid\
   - Rationale: Balances computational cost with urban-scale resolution needs\
   \
4. **Forecast Horizon**: 72 hours (with 120-hour option)\
   - Rationale: Matches GEOS-CF availability and operational needs\
\
### Technology Stack\
\
- **Language**: Python 3.9+\
- **Core Libraries**: numpy, xarray, pytorch\
- **Data Access**: earthaccess\
- **ML Framework**: deepsensor\
- **Deployment**: NASA NCCS (Discover/ADAPT)\
- **Version Control**: Git (GitHub)\
\
## Data Sources Summary\
\
### Satellite Data\
| Source | Product | Variables | Resolution | Latency |\
|--------|---------|-----------|------------|---------|\
| VIIRS MAIAC | VNP09GA | AOD | 1 km | 1-2 days |\
| TROPOMI | S5P_L2 | NO\uc0\u8322 , O\u8323  | 7 km | 1-2 days |\
| PACE | PACE_OCI_L2 | NO\uc0\u8322 , O\u8323  | 1 km | 1-2 days |\
| GOES-ABI | ABI-L2-AOD | AOD | 2 km | 1 hour |\
| TEMPO | TEMPO_L2 | NO\uc0\u8322 , O\u8323  profile | 2-8 km | 1 hour |\
\
### Model Data\
| Source | Variables | Resolution | Forecast Horizon |\
|--------|-----------|------------|------------------|\
| GEOS-CF | PM2.5, O\uc0\u8323 , NO\u8322 , met | 25 km | 120 hours |\
\
### Ground Data\
| Source | Variables | Temporal Resolution | Coverage |\
|--------|-----------|---------------------|----------|\
| AirNow | PM2.5, O\uc0\u8323 , NO\u8322  | Hourly | U.S. |\
| OpenAQ | PM2.5, O\uc0\u8323 , NO\u8322  | Hourly | Global |\
\
## Resource Requirements\
\
### Storage (NCCS)\
- Historical data: ~500 GB per region per year\
- Model weights: ~1 GB per trained model\
- Forecast outputs: ~10 GB per region per month\
- **Total estimated**: 1-2 TB per region\
\
### Compute (NCCS)\
- **Training**: 1 GPU node, 24 hours per model\
- **Daily forecasting**: 1 CPU node, 2 hours per region\
- **Data processing**: 1 CPU node, 4 hours per day\
\
## Risk Assessment\
\
### Technical Risks\
\
| Risk | Probability | Impact | Mitigation |\
|------|-------------|--------|------------|\
| Data availability issues | Medium | High | Implement fallback data sources, robust error handling |\
| Model performance below expectations | Medium | High | Extensive validation, ensemble methods, iterative improvement |\
| NCCS resource constraints | Low | Medium | Optimize code, request adequate allocation |\
| DeepSensor integration challenges | Medium | Medium | Early prototyping, community support |\
\
### Operational Risks\
\
| Risk | Probability | Impact | Mitigation |\
|------|-------------|--------|------------|\
| API rate limits | Medium | Medium | Implement caching, request optimization |\
| Data latency issues | Medium | Medium | Monitor data availability, adjust schedules |\
| Credential management | Low | High | Secure storage, documentation, backup procedures |\
\
## Success Metrics\
\
### Technical Metrics\
- **Forecast Accuracy**: RMSE < 20% of observed range\
- **Forecast Bias**: MNB < 10%\
- **Forecast Correlation**: R-squared > 0.75, spatial and temporal correlation each above 0.6\
- **Spatial Coverage**: > 90% of monitoring sites\
- **Temporal Coverage**: > 95% of forecast periods\
- **Confidence Calibration**: 90% CI coverage within 85-95%\
\
### Operational Metrics\
- **Update Frequency**: Daily forecasts without interruption\
- **Latency**: Forecasts available within 6 hours of data availability\
- **Reliability**: > 99% uptime for automated workflows\
\
### Development Metrics\
- **Code Coverage**: > 80% unit test coverage\
- **Documentation**: 100% of public APIs documented\
- **Security**: Zero critical vulnerabilities\
\
## Communication Plan\
\
### Documentation\
- **Code**: Inline comments and docstrings\
- **API**: Auto-generated from docstrings\
- **User**: Markdown documentation in docs/\
- **Project**: This file (PROJECT.md)\
\
## Version History\
\
| Version | Date | Description |\
|---------|------|-------------|\
| 0.0.1-dev | Nov 2026 | Initial development version |\
}