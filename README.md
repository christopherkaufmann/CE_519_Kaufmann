# CE 519 Concrete Pavement Design, LCC, LCA, Uncertainty, and Selection Program

## 1. Introduction

This technical document describes the methodology and implementation of a mechanistic and life-cycle-based evaluation program for concrete pavement systems. The program compares steel reinforced concrete (SRC) and fiber reinforced concrete (FRC) alternatives for a defined CE 519 project footprint. The workflow includes structural design, life-cycle cost analysis (LCCA), life-cycle assessment (LCA), uncertainty and sensitivity analysis, optimization/selection, and a planned summary graphics module. All calculations are executed from the parent-level `Program_Control.ipynb` notebook, which coordinates Modules 1 through 7. This program directly implements the methodologies defined in CE 519 Deliverables 3 through 6, with Module 7 reserved for future summary-output graphics.

## 2. Project Definition

The pavement system consists of a 300 ft by 150 ft parking lot and 2,050 linear ft of 20 ft wide roadway. The resulting project pavement area is 86,000 sf. The design axle load is 19 kip, which is idealized as two 9.5 kip wheel loads. The subbase material is limited to #57 stone. At the end of the service life, the pavement is assumed to be fully demolished and crushed for reuse as aggregate.

```text
Parking lot area = 300 ft × 150 ft = 45,000 sf
Roadway area = 2,050 ft × 20 ft = 41,000 sf
Total pavement area = 86,000 sf
Design axle load = 19 kip
Design wheel load = 9.5 kip
Subbase material = #57 stone
```

## 3. Program Structure

```text
ce519_program/
│
├── Program_Control.ipynb
├── README.md
│
├── module_1/  Steel reinforced concrete pavement design
├── module_2/  Fiber reinforced concrete pavement design
├── module_3/  Life-cycle costing
├── module_4/  Life-cycle assessment
├── module_5/  Uncertainty and sensitivity analysis
├── module_6/  Optimization and selection
├── module_7/  Summary output graphics (Not Yet Implemented)
│
└── outputs/
```

## 3.1 Deliverable-to-Module Linkage

```text
Module 1: Steel reinforced concrete pavement design -> Deliverable 3, Basis of Design
Module 2: Fiber reinforced concrete pavement design -> Deliverable 3, Basis of Design
Module 3: Life-cycle cost analysis -> Deliverable 4, LCC Methodology
Module 4: Life-cycle assessment -> Deliverable 5, LCA Methodology
Module 5: Uncertainty and sensitivity analysis -> Deliverable 6, Uncertainty & Sensitivity Analyses
Module 6: Optimization and selection -> applies the outputs from Modules 1 through 5 for final alternative selection
Module 7: Summary output graphics -> Not Yet Implemented; planned post-processing of Modules 1 through 6
```

## 4. Module 1: Steel Reinforced Concrete Pavement Design

Module 1 evaluates discrete SRC pavement alternatives. Pavement stresses are calculated using Westergaard slab-on-grade theory with edge loading as the governing condition.

```text
σe = (0.572P / h²) [4log10(l / b) + 0.359]
```

where:

```text
P = wheel load, lb
h = slab thickness, in.
l = radius of relative stiffness, in.
b = equivalent resisting radius, in.
```

The radius of relative stiffness is:

```text
l = [Ec h³ / (12k(1 − μ²))]^0.25
```

The tire contact radius is:

```text
a = √(P / (πp))
```

The equivalent resisting radius is:

```text
b = √(1.6a² + h²) − 0.675h     for a < 1.724h
b = a                           for a ≥ 1.724h
```

SRC flexural capacity is calculated using ACI 318 rectangular stress block methodology.

```text
a = As fy / (0.85 f'c b)
Mn = As fy (d − a/2)
φMn = φ Mn
```

Reinforcement quantity assumptions include 40 ft stock bar lengths, Class A lap splices, two-way reinforcement in the parking lot, and one-way reinforcement in the roadway.

## 5. Module 2: Fiber Reinforced Concrete Pavement Design

Module 2 evaluates discrete FRC pavement alternatives. FRC capacity is calculated using both the plain concrete flexural contribution and the residual fiber contribution.

```text
Mcr = fr b h² / 6
Mn-FRC = fe3 b h² / 6
Mtotal = Mcr + Mn-FRC
φMtotal = φ Mtotal
```

The residual strength input `fe3` is treated as the FRC performance variable. TUF-STRAND SF dosage is estimated from the accepted project relationship:

```text
dosage, lb/yd³ = 0.03(fe3) − 1.1
```

The dosage is bounded to Euclid Chemical's typical TUF-STRAND SF dosage range of 3 to 20 lb/yd³.

## 6. Module 3: Life-Cycle Cost Analysis

Module 3 calculates deterministic present-worth cost for feasible SRC and FRC alternatives. Costs are based on RSMeans-style construction cost inputs with a Saginaw County, Michigan location factor. The baseline economic period is 50 years and the baseline real discount rate is 3%, consistent with Deliverable 4. The model includes concrete, #57 stone, reinforcing steel, TUF-STRAND SF fiber, demolition, crushing, and end-of-life reuse credit. Maintenance is set to zero by project basis.

For a one-time future cost:

```text
PV factor = 1 / (1 + r)^n
```

The total present worth is:

```text
PW = Initial Cost + Maintenance PW + End-of-Life PW
```

For this project:

```text
Maintenance PW = 0
```

FRC fiber cost is calculated using the contract unit price:

```text
fiber cost = concrete volume × dosage × $1.47/lb baseline
```

The fiber pricing source is the Parsons Corporation Euclid Chemical Pricing Agreement, February 2026. The deterministic baseline uses the maximum documented contract value of $1.47/lb. Module 5 samples the documented $1.323 to $1.47/lb range to represent uncertainty and a potential volume-discount reduction from the conservative baseline price.

## 7. Module 4: Life-Cycle Assessment

Module 4 calculates total project climate change impact in kg CO2-eq. The functional unit is one complete CE 519 pavement project consisting of 86,000 sf of pavement.

Included processes are:

```text
Ready-mix concrete production
#57 stone production
Fabricated reinforcing steel production using CRSI EPD A1-A3
TUF-STRAND SF production
Concrete hauling to the project site
#57 stone hauling to the project site
Rebar hauling from Nucor Marion, OH to HYMMCO, then HYMMCO to the project site
End-of-life demolition
Crushed concrete hauling
Concrete crushing for reuse as aggregate
```

Excluded processes are:

```text
Maintenance
Fiber hauling, because fiber is assumed to be included with admixture delivery
Construction equipment other than explicit demolition energy/emissions
```

The CRSI EPD value used for fabricated reinforcing steel is:

```text
854 kg CO2-eq / metric ton fabricated rebar
774.736 kg CO2-eq / short ton fabricated rebar
```

The TUF-STRAND SF GWP value used is:

```text
3.08 kg CO2-eq / kg fiber
```

## 8. Module 5: Uncertainty and Sensitivity Analysis

Module 5 performs Monte Carlo uncertainty analysis and Spearman rank sensitivity analysis. The default simulation count is 50,000 and the random seed is 42. The primary outputs are total present worth and total project GWP.

Uncertain parameters include:

```text
concrete unit cost
#57 stone unit cost
rebar unit cost
fiber unit cost
demolition cost
crushing cost
recycled aggregate credit
discount rate
concrete GWP factor
#57 stone GWP factor
rebar GWP factor
trucking GWP factor
demolition GWP factor
crushing GWP factor
```

Uniform distributions are used for bounded cost values, a truncated normal distribution is used for the discount rate, and scaled beta distributions are used for bounded GWP multipliers. Fiber unit cost uncertainty is based on the contract value with a volume discount range:

```text
fiber unit cost ~ Uniform(1.323, 1.47) $/lb
```

### Uncertainty Parameter Table

| Parameter | Distribution | Values Defining Distribution | Units | Reference |
|---|---:|---:|---:|---|
| Concrete unit cost | Uniform | 150 to 230 | $/cy | RSMeans / Gordian 2026 screening range |
| #57 stone unit cost | Uniform | 45 to 75 | $/cy | RSMeans / Gordian 2026 screening range |
| Rebar unit cost | Uniform | 2,600 to 3,900 | $/ton | RSMeans / Gordian 2026 screening range |
| Fiber unit cost | Uniform | 1.323 to 1.47 | $/lb | Parsons Corporation / Euclid Chemical Pricing Agreement, 2026 |
| Demolition cost | Uniform | 32 to 55 | $/cy | RSMeans / Gordian 2026 screening range |
| Crushing cost | Uniform | 6 to 13 | $/ton | RSMeans / local recycler screening range |
| Recycled aggregate credit | Uniform | 3 to 9 | $/ton | Assumed local recycled aggregate value range |
| Discount rate | Truncated normal | mean = 0.03, std = 0.01, bounded 0.00 to 0.08 | decimal | FHWA LCCA practice |
| Concrete GWP factor | Scaled beta | alpha = 2, beta = 3, bounded 0.80 to 1.25 | multiplier | ecoinvent/APOS screening factor |
| #57 stone GWP factor | Scaled beta | alpha = 2, beta = 3, bounded 0.75 to 1.35 | multiplier | ecoinvent/APOS screening factor |
| Rebar GWP factor | Scaled beta | alpha = 2, beta = 3, bounded 0.75 to 1.35 | multiplier | CRSI fabricated rebar EPD screening factor |
| Trucking GWP factor | Scaled beta | alpha = 2, beta = 3, bounded 0.80 to 1.30 | multiplier | ecoinvent/APOS lorry transport screening factor |
| Demolition GWP factor | Scaled beta | alpha = 2, beta = 3, bounded 0.70 to 1.50 | multiplier | ecoinvent/APOS diesel equipment proxy |
| Crushing GWP factor | Scaled beta | alpha = 2, beta = 3, bounded 0.70 to 1.50 | multiplier | ecoinvent/APOS concrete crushing/recycling proxy |


## 9. Module 6: Optimization and Selection

Module 6 applies the final selection rule.

```text
Primary constraint: LCC ≤ 120% of the minimum deterministic LCC solution
Primary objective: minimize total project GWP, kg CO2-eq
```

The module reports the minimum-LCC benchmark solution, the selected FRC alternative, and the selected SRC alternative. If no SRC or FRC alternative satisfies the 120% LCC threshold, the lowest-LCA alternative for that category is still reported and flagged as outside the cost threshold.

## 10. Current Selection Interpretation

With the current design basis and input assumptions, the FRC alternative controls the benchmark cost and also provides the lowest LCA due to the corrected combined FRC capacity model. The SRC alternative is still reported for comparison under the Module 6 override rule when it exceeds the 120% LCC threshold.

## 11. References

1. American Concrete Institute (ACI). 2019. *ACI 318-19: Building Code Requirements for Structural Concrete*. Farmington Hills, MI.

2. American Concrete Institute (ACI). 2021. *ACI PRC-330-21: Commercial Concrete Parking Lots and Site Paving Design and Construction*. Farmington Hills, MI.

3. American Concrete Institute (ACI). 2018. *ACI 544.4R-18: Guide to Design with Fiber-Reinforced Concrete*. Farmington Hills, MI.

4. Fédération internationale du béton (fib). 2010. *fib Model Code for Concrete Structures 2010*. Lausanne, Switzerland.

5. Portland Cement Association (PCA). 1984. *Thickness Design for Concrete Highway and Street Pavements*. Skokie, IL.

6. Westergaard, H. M. 1926. “Stresses in Concrete Pavements Computed by Theoretical Analysis.” *Public Roads*.

7. National Programme on Technology Enhanced Learning (NPTEL). n.d. *Rigid Pavement Design Lecture Series: Wheel Load Stresses—Westergaard's Stress Equation*. Indian Institute of Technology.

8. Concrete Reinforcing Steel Institute (CRSI). 2022. *Industry-Wide Environmental Product Declaration: Fabricated Steel Reinforcement*. Schaumburg, IL.

9. Concrete Reinforcing Steel Institute (CRSI). 2022. *LCA Background Report for Industry-Wide Environmental Product Declaration: Fabricated Steel Reinforcement*. Schaumburg, IL.

10. Euclid Chemical Company. 2026. *TUF-STRAND SF Technical Data Sheet*. Cleveland, OH.

11. Euclid Chemical Company. 2026. *TUF-STRAND SF / FiberCalc Design Calculator*. Cleveland, OH.

12. Parsons Corporation. 2026. *Euclid Chemical Pricing Agreement*. February 2026.

13. Gordian. 2026. *RSMeans Building Construction Cost Data*. Greenville, SC.

14. Federal Highway Administration (FHWA). 2002. *Life-Cycle Cost Analysis Primer*. Washington, DC.

15. Federal Highway Administration (FHWA). 1998. *Life-Cycle Cost Analysis in Pavement Design: Interim Technical Bulletin*. Washington, DC.

16. Bare, J. 2012. “Tool for the Reduction and Assessment of Chemical and Other Environmental Impacts (TRACI), Version 2.1.” U.S. Environmental Protection Agency.

17. Wernet, G., Bauer, C., Steubing, B., Reinhard, J., Moreno-Ruiz, E., and Weidema, B. 2016. “The ecoinvent Database Version 3 (Part I): Overview and Methodology.” *International Journal of Life Cycle Assessment* 21:1218–1230.

18. ASTM International. 2021. *ASTM C1609/C1609M: Standard Test Method for Flexural Performance of Fiber-Reinforced Concrete (Using Beam with Third-Point Loading)*. West Conshohocken, PA.

## 12. Execution

Open `Program_Control.ipynb` and run the notebook from top to bottom. The notebook writes module outputs to the `outputs/` folder.


## 10. Module 7: Summary Output Graphics

Module 7 is reserved for future plotting and reporting utilities in `module_7/summary_output.py`. Current status: **Not Yet Implemented**. Planned graphics include structural feasibility plots, LCC/LCA comparison plots, uncertainty interval plots, sensitivity rankings, and final selection summary figures.
