"""
This script analyze the simulations generated by mc_get_spectra.py
it estimates the mean and numerical covariances from the simulations
"""


from pspy import pspy_utils, so_dict, so_spectra
import numpy as np
import sys

d = so_dict.so_dict()
d.read_from_file(sys.argv[1])

type = d["type"]
surveys = d["surveys"]
iStart = d["iStart"]
iStop = d["iStop"]
lmax = d["lmax"]
sim_alm_dtype = d["sim_alm_dtype"]

if sim_alm_dtype == "complex64":
    spec_dtype = np.float32
elif sim_alm_dtype == "complex128":
    spec_dtype = np.float64

spec_dir = "sim_spectra"
mcm_dir = "mcms"
mc_dir = "montecarlo"
cov_dir = "covariances"

pspy_utils.create_directory(mc_dir)
pspy_utils.create_directory(cov_dir)

spectra = ["TT", "TE", "TB", "ET", "BT", "EE", "EB", "BE", "BB"]

# we compute the full covariance matrix of the data
# for each sim we create two list, vec_list that include all power spectra and vec_list_restricted
# that includes only the TT,TE,EE spectra (also ET for cases where it is relevant)
# the mean and covariances of these vectors is computed and written to disc

for kind in ["cross", "noise", "auto"]:
    
    vec_list = []
    vec_list_restricted = []
    vec_list_EB = []

    for iii in range(iStart, iStop):
        vec = []
        vec_restricted = []
        vec_EB = []

        for spec in spectra:
            for id_sv1, sv1 in enumerate(surveys):
                arrays_1 = d[f"arrays_{sv1}"]
                for id_ar1, ar1 in enumerate(arrays_1):
                    for id_sv2, sv2 in enumerate(surveys):
                        arrays_2 = d[f"arrays_{sv2}"]
                        for id_ar2, ar2 in enumerate(arrays_2):

                            if  (id_sv1 == id_sv2) & (id_ar1 > id_ar2) : continue
                            if  (id_sv1 > id_sv2) : continue
                            if (sv1 != sv2) & (kind == "noise"): continue
                            if (sv1 != sv2) & (kind == "auto"): continue

                            spec_name = f"{type}_{sv1}_{ar1}x{sv2}_{ar2}_{kind}_%05d" %  iii

                            lb, Db = so_spectra.read_ps(spec_dir + f"/{spec_name}.dat", spectra=spectra)

                            n_bins = len(lb)
                            vec = np.append(vec, Db[spec])
                            
                            
                            if (sv1 == sv2) & (ar1 == ar2):
                                if spec == "TT" or spec == "EE" or spec == "TE" :
                                    vec_restricted = np.append(vec_restricted, Db[spec])
                            else:
                                if spec == "TT" or spec == "EE" or spec == "TE" or spec == "ET":
                                    vec_restricted = np.append(vec_restricted, Db[spec])
                            
                            if spec == "EB":
                                vec_EB = np.append(vec_EB, (Db["EB"] + Db["BE"])/2 )


        vec_list += [vec.astype(spec_dtype)]
        vec_list_restricted += [vec_restricted.astype(spec_dtype)]
        vec_list_EB += [vec_EB.astype(spec_dtype)]


    mean_vec = np.mean(vec_list, axis=0)
    mean_vec_restricted = np.mean(vec_list_restricted, axis=0)
    mean_vec_EB = np.mean(vec_list_EB, axis=0)

    cov = 0
    cov_restricted = 0
    cov_EB = 0

    for iii in range(iStart, iStop):
        cov += np.outer(vec_list[iii], vec_list[iii])
        cov_restricted += np.outer(vec_list_restricted[iii], vec_list_restricted[iii])
        cov_EB += np.outer(vec_list_EB[iii], vec_list_EB[iii])

    cov = cov / (iStop-iStart) - np.outer(mean_vec, mean_vec)
    cov_restricted = cov_restricted / (iStop-iStart) - np.outer(mean_vec_restricted, mean_vec_restricted)
    cov_EB = cov_EB / (iStop-iStart) - np.outer(mean_vec_EB, mean_vec_EB)

    np.save(f"{mc_dir}/cov_all_{kind}.npy", cov)
    np.save(f"{mc_dir}/cov_restricted_all_{kind}.npy", cov_restricted)
    np.save(f"{mc_dir}/cov_EB_all_{kind}.npy", cov_EB)

    id_spec = 0
    for spec in spectra:
        for id_sv1, sv1 in enumerate(surveys):
            arrays_1 = d[f"arrays_{sv1}"]
            for id_ar1, ar1 in enumerate(arrays_1):
                for id_sv2, sv2 in enumerate(surveys):
                    arrays_2 = d[f"arrays_{sv2}"]
                    for id_ar2, ar2 in enumerate(arrays_2):
                    
                    
                        if  (id_sv1 == id_sv2) & (id_ar1 > id_ar2) : continue
                        if  (id_sv1 > id_sv2) : continue
                        if (sv1 != sv2) & (kind == "noise"): continue
                        if (sv1 != sv2) & (kind == "auto"): continue

                        mean = mean_vec[id_spec * n_bins:(id_spec + 1) * n_bins]
                        std = np.sqrt(cov[id_spec * n_bins:(id_spec + 1) * n_bins, id_spec * n_bins:(id_spec + 1) * n_bins].diagonal())
                        
                        np.savetxt(f"{mc_dir}/spectra_{spec}_{sv1}_{ar1}x{sv2}_{ar2}_{kind}.dat", np.array([lb, mean, std]).T)
                                   
                        id_spec += 1

