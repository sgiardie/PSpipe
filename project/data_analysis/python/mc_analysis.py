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

spec_dir = "sim_spectra"
mcm_dir = "mcms"
mc_dir = "montecarlo"
cov_dir = "covariances"

pspy_utils.create_directory(mc_dir)
pspy_utils.create_directory(cov_dir)

spectra = ["TT", "TE", "TB", "ET", "BT", "EE", "EB", "BE", "BB"]

for kind in ["cross", "noise", "auto"]:
    
    vec_list = []
    vec_list_restricted = []

    for iii in range(iStart, iStop):
        vec = []
        vec_restricted = []
        for spec in spectra:
            for id_sv1, sv1 in enumerate(surveys):
                arrays_1 = d["arrays_%s" % sv1]
                for id_ar1, ar1 in enumerate(arrays_1):
                    for id_sv2, sv2 in enumerate(surveys):
                        arrays_2 = d["arrays_%s" % sv2]
                        for id_ar2, ar2 in enumerate(arrays_2):

                            if  (id_sv1 == id_sv2) & (id_ar1 > id_ar2) : continue
                            if  (id_sv1 > id_sv2) : continue
                            if (sv1 != sv2) & (kind == "noise"): continue
                            if (sv1 != sv2) & (kind == "auto"): continue

                            spec_name = "%s_%s_%sx%s_%s_%s_%05d" % (type, sv1, ar1, sv2, ar2, kind, iii)
                            
                            lb, Db = so_spectra.read_ps(spec_dir + "/%s.dat" % spec_name, spectra=spectra)

                            n_bins = len(lb)
                            vec = np.append(vec, Db[spec])
                            
                            if (sv1 == sv2) & (ar1 == ar2):
                                if spec == "TT" or spec == "EE" or spec == "TE" :
                                    vec_restricted = np.append(vec_restricted, Db[spec])
                            else:
                                if spec == "TT" or spec == "EE" or spec == "TE" or spec == "ET":
                                    vec_restricted = np.append(vec_restricted, Db[spec])

                                
        vec_list += [vec]
        vec_list_restricted += [vec_restricted]

    mean_vec = np.mean(vec_list, axis=0)
    mean_vec_restricted = np.mean(vec_list_restricted, axis=0)

    cov = 0
    cov_restricted = 0

    for iii in range(iStart, iStop):
        cov += np.outer(vec_list[iii], vec_list[iii])
        cov_restricted += np.outer(vec_list_restricted[iii], vec_list_restricted[iii])

    cov = cov / (iStop-iStart) - np.outer(mean_vec, mean_vec)
    cov_restricted = cov_restricted / (iStop-iStart) - np.outer(mean_vec_restricted, mean_vec_restricted)

    np.save("%s/cov_all_%s.npy" % (mc_dir, kind), cov)
    np.save("%s/cov_restricted_all_%s.npy" % (mc_dir, kind), cov_restricted)

    id_spec = 0
    for spec in spectra:
        for id_sv1, sv1 in enumerate(surveys):
            arrays_1 = d["arrays_%s" % sv1]
            for id_ar1, ar1 in enumerate(arrays_1):
                for id_sv2, sv2 in enumerate(surveys):
                    arrays_2 = d["arrays_%s" % sv2]
                    for id_ar2, ar2 in enumerate(arrays_2):
                    
                    
                        if  (id_sv1 == id_sv2) & (id_ar1 > id_ar2) : continue
                        if  (id_sv1 > id_sv2) : continue
                        if (sv1 != sv2) & (kind == "noise"): continue
                        if (sv1 != sv2) & (kind == "auto"): continue

                        mean = mean_vec[id_spec * n_bins:(id_spec + 1) * n_bins]
                        std = np.sqrt(cov[id_spec * n_bins:(id_spec + 1) * n_bins, id_spec * n_bins:(id_spec + 1) * n_bins].diagonal())
                        
                        np.savetxt("%s/spectra_%s_%s_%sx%s_%s_%s.dat" % (mc_dir, spec, sv1, ar1, sv2, ar2, kind), np.array([lb,mean,std]).T)
                                   
                        id_spec += 1


spec_list = []
for id_sv1, sv1 in enumerate(surveys):
    arrays_1 = d["arrays_%s" % sv1]
    for id_ar1, ar1 in enumerate(arrays_1):
        for id_sv2, sv2 in enumerate(surveys):
            arrays_2 = d["arrays_%s" % sv2]
            for id_ar2, ar2 in enumerate(arrays_2):
                if  (id_sv1 == id_sv2) & (id_ar1 > id_ar2) : continue
                if  (id_sv1 > id_sv2) : continue
                spec_list += ["%s_%sx%s_%s" % (sv1, ar1, sv2, ar2)]
            
for sid1, spec1 in enumerate(spec_list):
    for sid2, spec2 in enumerate(spec_list):
        if sid1 > sid2 : continue
        na, nb = spec1.split("x")
        nc, nd = spec2.split("x")
        
        ps_list_ab = []
        ps_list_cd = []
        for iii in range(iStart, iStop):
            spec_name_cross_ab = "%s_%sx%s_cross_%05d" % (type, na, nb, iii)
            spec_name_cross_cd = "%s_%sx%s_cross_%05d" % (type, nc, nd, iii)
        
            lb, ps_ab = so_spectra.read_ps(spec_dir + "/%s.dat" % spec_name_cross_ab, spectra=spectra)
            lb, ps_cd = so_spectra.read_ps(spec_dir + "/%s.dat" % spec_name_cross_cd, spectra=spectra)
    
            vec_ab = []
            vec_cd = []
            for spec in ["TT", "TE", "ET", "EE"]:
                vec_ab = np.append(vec_ab, ps_ab[spec])
                vec_cd = np.append(vec_cd, ps_cd[spec])
    
            ps_list_ab += [vec_ab]
            ps_list_cd += [vec_cd]

        cov_mc = 0
        for iii in range(iStart, iStop):
            cov_mc += np.outer(ps_list_ab[iii], ps_list_cd[iii])

        cov_mc = cov_mc / (iStop-iStart) - np.outer(np.mean(ps_list_ab, axis=0), np.mean(ps_list_cd, axis=0))

        np.save("%s/mc_cov_%sx%s_%sx%s.npy"%(cov_dir, na, nb, nc, nd), cov_mc)

