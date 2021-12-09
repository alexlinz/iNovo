###################
# run_standard_dFBA.py
# Copyright 2021, Alexandra Linz, Daniel Noguera, and Timothy Donohue
# Contact: amlinz@wisc.edu
#
# This script takes user input and a previously build model and runs dynamic flux balance analysis to user specifications
# Its output is a dataframe that can be plotted with a separate script
###################

# Import packages
import cobra
from cobra.flux_analysis.loopless import loopless_solution
import logging
import pandas
import copy
logging.basicConfig()
cobra_config = cobra.Configuration()
cobra_config.solver = "glpk_exact"

# Some warnings you may see
# "Solver status infeasible" - happens when a constraint cannot be meant. Most often when no S compounds are being consumed
# "Maximum allowed rate exceeds remaining concentration of substrate - resetting max rate"
# This means that the maximum uptake rate for a substrate would take up more substrate than is currently available if allowed to operate at that max rate. Instead, its max rate is revised so that it can take up the exact amount available and no more.
# "uptake rate is limiting" - a non-carbon substrate is operating at its maximum allowed uptake rate
# Usually indicates that something besides the carbon is limiting growth

###############
# EDIT THIS SECTION BEFORE RUNNING
culture_volume = 0.025 			# volume in L
starting_biomass = 0.001 			# in g/L
gene_deletions = [] 			# add any gene deletions you'd like the model to perform here
substrates = {"exVA": [1.0], "exSA": [1.0], "expHBA": [1.0]}  # use CPD ID followed by concentration in mmol/L
timepoint_interval = 15 			# minutes between timepoints
n  = 75  				#number of timesteps

model_path = "/Users/Alex/Desktop/iNovo/Model_builds/Models/iNovo.xml"
output_path = "/Users/Alex/Desktop/iNovo/Model_results/SA_VA_pHBA_"

##############
# THINGS YOU PROBABLY WON'T NEED TO EDIT BUT CAN
# This encodes Standard Mineral Base, no carbon, from DSMZ Medium 1185. Iron, ammonia, phosphate, and sulfate.
media_components = {"exC14818": [45.54], "exC00014": [10.], "exC00009": [26.1], "exC00059": [8.]}
# These are exchange reactions that are far in excess of others due to diffusion
enviro = {"C00282": [10], "exC00001": [100], "exC00007": [10]}
# These are things the model needs to be allowed to output or it will break - your run may not need all of these
# "Guaiacol": [0], "C00127": [0],"C04425": [0], "C05198": [0], "C00153": [0], "C00011": [0],
#outfluxes = {"C00162": [1], "C00010": [1], "C00132": [0], "C00054": [0], "PDC": [0], "C00011": [0], "C05198": [0], "C04425": [0], "C00266": [0], "C00153": [0]}
outfluxes = {"C00067": [0], "C00058": [0], "C00033": [0], "C00010": [1], "C00162": [1], "C00010": [1], "C00132": [0], "C00054": [0], "C00011": [0], "C05198": [0], "C04425": [0], "C00266": [0], "C00153": [0]}


# Kinetic parameters in mM per min - these are estimates from related bacteria in the literature and not experimentally verified
nonaromatic_substrates = ["exC00031", "exC00243", "exC00033", "exC00022", "exC00095", "exC00181", "exC00208", "exC00185"]

def get_rate(cpd_ID):
    global Vm
    global Ks
    # glucose
    if cpd_ID in nonaromatic_substrates:
        Vm = 0.5
        Ks = 0.139
        Ki = 0.139
    # aromatics
    # S-type
    elif cpd_ID == "exSA" or cpd_ID == "exS" or cpd_ID == "exSDK":
        Vm = 0.582
        Ks = 0.05
        Ki = 0.05
    # H-type
    elif cpd_ID == "expHBA" or cpd_ID == "exPCA" or cpd_ID == "exC00633" or cpd_ID == "exC00180"or cpd_ID == "exC00156":
        Vm = 0.902
        Ks = 0.05
        Ki = 0.05
    # G-type
    elif cpd_ID == "exVA" or cpd_ID == "exV" or cpd_ID == "exFA" or cpd_ID == "exGDK" or cpd_ID == "exSRGGE":
        Vm = 0.569
        Ks = 0.1
        Ki = 0.1
    # ammonia
    elif cpd_ID == "exC00014":
        Vm = 0.5
        Ks = 0.1
        Ki = 0.1
    # phosphate
    elif cpd_ID == "exC00009":
        Vm = 0.060
        Ks = 0.002
        Ki = 0.1
    # sulfate
    elif cpd_ID == "exC00059":
        Vm = 0.0017
        Ks = 0.003
        Ki = 0.1
    # iron
    elif cpd_ID == "exC14818":
        Vm = 0.0017
        Ks = 0.003
        Ki = 0.1
    else:
        Vm = 0
        Ks = 0
        Ki = 0.1
    return Vm, Ks, Ki


##############
# Load and set up the model
Novo_model = cobra.io.read_sbml_model(model_path)
media_components.update(substrates) # Add carbon sources to the basic medium recipe

# Add media components, cofactors, virtually unlimited influxes, and outfluxes to the model as exchange reactions
for item in media_components.keys():

    new_exchange = "EX_" + item
    Novo_model.add_boundary(Novo_model.metabolites.get_by_id(item), type = "exchange",  ub = 50000., reaction_id=new_exchange)

for item in enviro:

    new_enviro = "EX_" + item
    Novo_model.add_boundary(Novo_model.metabolites.get_by_id(item), ub = 100000., type = "exchange", reaction_id=new_enviro)

for item in outfluxes:
    new_outflux = "DM_" + item
    Novo_model.add_boundary(Novo_model.metabolites.get_by_id(item), ub = 1000., type = "demand", reaction_id=new_outflux)

# Set the model objective
Novo_model.objective = Novo_model.reactions.get_by_id("biomass")

# Add any constraints
# Constraint 1: CCMA pathway is 5% of the PDC pathway

CCMA_flux = Novo_model.problem.Constraint(
    Novo_model.reactions.A033.flux_expression - Novo_model.reactions.A005.flux_expression * 0.15,
    lb=0,
    ub=0)
Novo_model.add_cons_vars(CCMA_flux)

# Miguel's new S pathway should operate at 15% flux of the main pathway
SA_flux = Novo_model.problem.Constraint(
    Novo_model.reactions.A031.flux_expression - Novo_model.reactions.A015.flux_expression * 0.15,
    lb=0,
    ub=0)
Novo_model.add_cons_vars(SA_flux)

# Set the non-growth associated maintenance requirement
Novo_model.reactions.get_by_id("NGAM").upper_bound = 0.00004
Novo_model.reactions.get_by_id("NGAM").lower_bound = 0.00004


############

# Combine all tracked items and add time to the tracking dictionary
tracking = copy.deepcopy(media_components)
tracking.update(enviro)
tracking.update(outfluxes)
tracking["Time"] = [0]
tracking["Biomass"] = [starting_biomass]


#############
# Set up your gene deletions

if len(gene_deletions) > 0:

    for gene in range(0, len(gene_deletions)):

        exec("Novo_model.genes." + gene_deletions[gene] + ".knock_out()")

#############
# Run the wild type model (plus your gene deletions of choice)

out = {}
out2 = {}
track_rates = copy.deepcopy(substrates)
track_rates.update(media_components)

for i in range(1,n):
    if i%10 == 0:
        print(i)

    for metabolite in tracking:

        if metabolite in substrates or metabolite in media_components:

            if metabolite in substrates:
                if tracking[metabolite][i - 1] < 0.0000001:
                    r = 0.0
                    tracking[metabolite][i - 1] = 0.0

                else:
                    r = get_rate(metabolite)[0] * (tracking[metabolite][i - 1] / ((tracking[metabolite][i - 1] + get_rate(metabolite)[1]) * ( 1 + tracking[metabolite][i - 1] / get_rate(metabolite)[2])))

            else:
                r = get_rate(metabolite)[0] * (tracking[metabolite][i - 1] / ((tracking[metabolite][i - 1] + get_rate(metabolite)[1]) ))

            if tracking[metabolite][i - 1] < (r *  tracking["Biomass"][i-1] * timepoint_interval):
                print("Maximum allowed rate exceeds remaining concentration of substrate - resetting max rate ", i, "; ", metabolite, "; ", r)
                r = tracking[metabolite][i - 1] / (tracking["Biomass"][i-1] * timepoint_interval)


            exec ("Novo_model.reactions.EX_" + metabolite + ".lower_bound = -1 * r")
            exec ("Novo_model.reactions.EX_" + metabolite + ".upper_bound = 1 * r")
            exec ("track_rates[metabolite].append(Novo_model.reactions.EX_" + metabolite + ".upper_bound)")

        if tracking[metabolite][i - 1] <= 0. and metabolite != "Time" and metabolite not in outfluxes:
            exec ("Novo_model.reactions.EX_" + metabolite + ".upper_bound = 0.")
            exec ("Novo_model.reactions.EX_" + metabolite + ".lower_bound = 0.")

    opt = Novo_model.optimize()
    solution = loopless_solution(Novo_model)
    out[i] = solution.fluxes

    # Track biomass
    tracking["Biomass"].append(tracking["Biomass"][i - 1] + out[i]["biomass"] * tracking["Biomass"][i - 1] * timepoint_interval)

    # Print warning if any metabolite is at its maximum allowed rate
    # Do not do this for the carbon, as that should be limiting
    for metabolite in media_components:
        exec ("upper_limit = Novo_model.reactions.EX_" + metabolite + ".upper_bound")
        exec ("lower_limit = Novo_model.reactions.EX_" + metabolite + ".lower_bound")
        exec("rate = out[i][\"EX_" + metabolite + "\"]")

        if (rate == upper_limit and rate != 0) or (rate == lower_limit and rate != 0):
            print(str(i) + ": " + metabolite + " uptake rate is limiting" + ": " + str(rate))

    for metabolite in enviro:
        exec ("upper_limit = Novo_model.reactions.EX_" + metabolite + ".upper_bound")
        exec ("lower_limit = Novo_model.reactions.EX_" + metabolite + ".lower_bound")
        exec("rate = out[i][\"EX_" + metabolite + "\"]")

        if (rate == upper_limit and rate != 0) or (rate == lower_limit and rate != 0):
            print(str(i) + ": " + metabolite + " uptake rate is limiting" + ": " + str(rate))

    for metabolite in outfluxes:
        exec ("upper_limit = Novo_model.reactions.DM_" + metabolite + ".upper_bound")
        exec ("lower_limit = Novo_model.reactions.DM_" + metabolite + ".lower_bound")
        exec("rate = out[i][\"DM_" + metabolite + "\"]")

        if (rate == upper_limit and rate != 0) or (rate == lower_limit and rate != 0):
            print(str(i) + ": " + metabolite + " uptake rate is limiting" + ": " + str(rate))

    # Mass balance items in tracking

    for metabolite in tracking:
        if metabolite == "Time":
            tracking["Time"].append(tracking["Time"][-1] + timepoint_interval)
        elif metabolite == "Biomass":
             continue
        elif metabolite in outfluxes:
            exec ("tracking[metabolite].append(tracking[metabolite][i - 1] + out[i][\"DM_" + metabolite + "\"] * tracking[\"Biomass\"][i - 1] * timepoint_interval)")
        elif metabolite in substrates:
            exec ("tracking[metabolite].append(tracking[metabolite][i - 1] + out[i][\"EX_" + metabolite + "\"] * tracking[\"Biomass\"][i - 1] * timepoint_interval)")

        else:
            exec("tracking[metabolite].append(tracking[metabolite][i - 1] + out[i][\"EX_" + metabolite + "\"] * tracking[\"Biomass\"][i - 1] * timepoint_interval)")


    # Optional: print the fluxes at a certain iteration. Helpful for troubleshooting
    #if i == 2 or i == 90 or i == 156:
    #       exec("solution.fluxes.to_csv(output_path + \"fluxes" + str(i) + ".csv\")")

    # Print warning if biomass is operating in reverse
    if out[i]["biomass"] < 0.0:
        print(i)
        print("Biomass running in reverse")
        break

# Output tracking dictionary as a dataframe
df = pandas.DataFrame.from_dict(tracking, orient = "index").transpose()
track_rates2 = pandas.DataFrame.from_dict(track_rates, orient = "index").transpose()

df.to_csv(output_path + "dFBA_results.csv")


