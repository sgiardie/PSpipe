"""
This script generate simplistic simulations of the actpol data
it generates gaussian simulations of cmb, fg and noise
the fg is based on fgspectra, and the noise is based on the 1d noise power spectra measured on the data
"""

from pspy import pspy_utils, so_dict, so_map, sph_tools, so_mcm, so_spectra, so_mpi, so_map_preprocessing
import numpy as np
import sys
import time
from pixell import curvedsky, powspec
from pspipe_utils import simulation, pspipe_list, best_fits, kspace, misc



d = so_dict.so_dict()
d.read_from_file(sys.argv[1])

surveys = d["surveys"]
lmax = d["lmax"]
niter = d["niter"]
type = d["type"]
binning_file = d["binning_file"]
write_all_spectra = d["write_splits_spectra"]
sim_alm_dtype = d["sim_alm_dtype"]
binned_mcm = d["binned_mcm"]
apply_kspace_filter = d["apply_kspace_filter"]

if sim_alm_dtype == "complex64": sim_alm_dtype = np.complex64
elif sim_alm_dtype == "complex128": sim_alm_dtype = np.complex128

window_dir = "windows"
mcm_dir = "mcms"
spec_dir = "sim_spectra"
bestfit_dir = "best_fits"
noise_model_dir = "noise_model"

pspy_utils.create_directory(spec_dir)

spectra = ["TT", "TE", "TB", "ET", "BT", "EE", "EB", "BE", "BB"]
spin_pairs = ["spin0xspin0", "spin0xspin2", "spin2xspin0", "spin2xspin2"]

# prepare the tempalte and the filter
arrays, templates, filters, n_splits, filter_dicts = {}, {}, {}, {}, {}
spec_name_list = pspipe_list.get_spec_name_list(d, char="_")

for sv in surveys:
    arrays[sv] = d[f"arrays_{sv}"]
    template_name = d[f"window_T_{sv}_{arrays[sv][0]}"]
    n_splits[sv] = d[f"n_splits_{sv}"]
    print(f"Running with {n_splits[sv]} splits for survey {sv}")
    templates[sv] = so_map.read_map(template_name)
    templates[sv].set_ncomp(3)

    if apply_kspace_filter & (templates[sv].pixel == "CAR"):
        filter_dicts[sv] = d[f"k_filter_{sv}"]
        filters[sv] = kspace.get_kspace_filter(templates[sv], filter_dicts[sv])

if apply_kspace_filter:
    kspace_tf_path = d["kspace_tf_path"]
    if kspace_tf_path == "analytical":
        kspace_transfer_matrix = kspace.build_analytic_kspace_filter_matrices(surveys,
                                                                              arrays,
                                                                              templates,
                                                                              filter_dicts,
                                                                              binning_file,
                                                                              lmax)
    else:
        kspace_transfer_matrix = {}
        for spec_name in spec_name_list:
            kspace_transfer_matrix[spec_name] = np.load(f"{kspace_tf_path}/kspace_matrix_{spec_name}.npy", allow_pickle=True)


f_name_cmb = bestfit_dir + "/cmb.dat"
f_name_noise = noise_model_dir + "/mean_{}x{}_{}_noise.dat"
f_name_fg = bestfit_dir + "/fg_{}x{}.dat"

ps_mat = simulation.cmb_matrix_from_file(f_name_cmb, lmax, spectra)
array_list = [f"{sv}_{ar}" for sv in surveys for ar in arrays[sv]]
l, fg_mat = simulation.foreground_matrix_from_files(f_name_fg, array_list, lmax, spectra)

noise_mat = {}
for sv in surveys:
    l, noise_mat[sv] = simulation.noise_matrix_from_files(f_name_noise,
                                                          sv,
                                                          arrays[sv],
                                                          lmax,
                                                          n_splits[sv],
                                                          spectra)


# we will use mpi over the number of simulations
so_mpi.init(True)
subtasks = so_mpi.taskrange(imin=d["iStart"], imax=d["iStop"])

for iii in subtasks:
    print(f"Simulation n° {iii:05d}/{d['iStop']:05d}")
    print(f"-------------------------")
    t0 = time.time()

    # generate cmb alms and foreground alms
    # cmb alms will be of shape (3, lm) 3 standing for T,E,B
    # fglms will be of shape (nfreq, lm) and is T only

    alms_cmb = curvedsky.rand_alm(ps_mat, lmax=lmax, dtype="complex64")
    fglms = simulation.generate_fg_alms(fg_mat, array_list, lmax)

    master_alms = {}

    for sv in surveys:

        t1 = time.time()

        signal_alms = {}
        for ar in arrays[sv]:
            signal_alms[ar] = alms_cmb + fglms[f"{sv}_{ar}"]
            l, bl = pspy_utils.read_beam_file(d[f"beam_{sv}_{ar}"])
            signal_alms[ar] = curvedsky.almxfl(signal_alms[ar], bl)

        print(f"  Generate signal sim in {time.time() - t1:.02f} s")
        for k in range(n_splits[sv]):
            noise_alms = simulation.generate_noise_alms(noise_mat[sv], arrays[sv], lmax)
            for ar in arrays[sv]:

                t1 = time.time()

                win_T = so_map.read_map(d[f"window_T_{sv}_{ar}"])
                win_pol = so_map.read_map(d[f"window_pol_{sv}_{ar}"])
                window_tuple = (win_T, win_pol)
                del win_T, win_pol

                print(f"  [split {k}] Reading window in {time.time()-t1:.02f} s")

                t1 = time.time()
                split = sph_tools.alm2map(signal_alms[ar] + noise_alms[ar], templates[sv])
                print(f"  [split {k}] alm2map in {time.time()-t1:.02f} s")

                t1 = time.time()
                if sv in filters:

                        binary_file = misc.str_replace(d[f"window_T_{sv}_{ar}"], "window_", "binary_")
                        binary = so_map.read_map(binary_file)
                        split = kspace.filter_map(split,
                                                  filters[sv],
                                                  binary,
                                                  weighted_filter=filter_dicts[sv]["weighted"])

                        del binary
                print(f"  [split {k}] Filtering in {time.time()-t1:.02f} s")


                if d["remove_mean"] == True:
                    split = split.subtract_mean(window_tuple)

                t1 = time.time()
                master_alms[sv, ar, k] = sph_tools.get_alms(split, window_tuple, niter, lmax, dtype=sim_alm_dtype)
                print(f"  [split {k}] map2alm in {time.time()-t1:.02f} s")

    ps_dict = {}

    t1 = time.time()

    for id_sv1, sv1 in enumerate(surveys):
        for id_ar1, ar1 in enumerate(arrays[sv1]):
            for id_sv2, sv2 in enumerate(surveys):
                for id_ar2, ar2 in enumerate(arrays[sv2]):

                    if  (id_sv1 == id_sv2) & (id_ar1 > id_ar2) : continue
                    if  (id_sv1 > id_sv2) : continue

                    for spec in spectra:
                        ps_dict[spec, "auto"] = []
                        ps_dict[spec, "cross"] = []

                    mbb_inv, Bbl = so_mcm.read_coupling(prefix=f"{mcm_dir}/{sv1}_{ar1}x{sv2}_{ar2}",
                                                        spin_pairs=spin_pairs)

                    for s1 in range(n_splits[sv1]):
                        for s2 in range(n_splits[sv2]):
                            if (sv1 == sv2) & (ar1 == ar2) & (s1>s2) : continue


                            l, ps_master = so_spectra.get_spectra_pixell(master_alms[sv1, ar1, s1],
                                                                         master_alms[sv2, ar2, s2],
                                                                         spectra=spectra)

                            spec_name=f"{type}_{sv1}_{ar1}x{sv2}_{ar2}_{s1}{s2}"

                            lb, ps = so_spectra.bin_spectra(l,
                                                            ps_master,
                                                            binning_file,
                                                            lmax,
                                                            type=type,
                                                            mbb_inv=mbb_inv,
                                                            spectra=spectra,
                                                            binned_mcm=binned_mcm)

                            if (sv1 in filters) & (sv2 in filters):
                                lb, ps = kspace.deconvolve_kspace_filter_matrix(lb,
                                                                                ps,
                                                                                kspace_transfer_matrix[f"{sv1}_{ar1}x{sv2}_{ar2}"],
                                                                                spectra)

                            if write_all_spectra:
                                so_spectra.write_ps(spec_dir + "/%s_%05d.dat" % (spec_name,iii), lb, ps, type, spectra=spectra)

                            for count, spec in enumerate(spectra):
                                if (s1 == s2) & (sv1 == sv2):
                                    if count == 0:  print(f"  [auto] {sv1}_{ar1} X {sv2}_{ar2} {s1}{s2}")
                                    ps_dict[spec, "auto"] += [ps[spec]]
                                else:
                                    if count == 0: print(f"  [cross] {sv1}_{ar1} X {sv2}_{ar2} {s1}{s2}")
                                    ps_dict[spec, "cross"] += [ps[spec]]

                    ps_dict_auto_mean = {}
                    ps_dict_cross_mean = {}
                    ps_dict_noise_mean = {}

                    for spec in spectra:
                        ps_dict_cross_mean[spec] = np.mean(ps_dict[spec, "cross"], axis=0)
                        spec_name_cross = f"{type}_{sv1}_{ar1}x{sv2}_{ar2}_cross_%05d" % iii

                        if ar1 == ar2 and sv1 == sv2:
                            # Average TE / ET so that for same array same season TE = ET
                            ps_dict_cross_mean[spec] = (np.mean(ps_dict[spec, "cross"], axis=0) + np.mean(ps_dict[spec[::-1], "cross"], axis=0)) / 2.

                        if sv1 == sv2:
                            ps_dict_auto_mean[spec] = np.mean(ps_dict[spec, "auto"], axis=0)
                            spec_name_auto = f"{type}_{sv1}_{ar1}x{sv2}_{ar2}_auto_%05d" % iii
                            ps_dict_noise_mean[spec] = (ps_dict_auto_mean[spec] - ps_dict_cross_mean[spec]) / n_splits[sv1]
                            spec_name_noise = f"{type}_{sv1}_{ar1}x{sv2}_{ar2}_noise_%05d" % iii

                    so_spectra.write_ps(spec_dir + "/%s.dat" % spec_name_cross, lb, ps_dict_cross_mean, type, spectra=spectra)

                    if sv1 == sv2:
                        so_spectra.write_ps(spec_dir+"/%s.dat" % spec_name_auto, lb, ps_dict_auto_mean, type, spectra=spectra)
                        so_spectra.write_ps(spec_dir+"/%s.dat" % spec_name_noise, lb, ps_dict_noise_mean, type, spectra=spectra)

    print(f"  Spectra computation in {time.time()-t1:.02f} s")
    print(f"  Simulation n° {iii:05d} done in {time.time()-t0:.02f} s")
    print("")
