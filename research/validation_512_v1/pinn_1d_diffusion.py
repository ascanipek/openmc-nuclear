"""Controlled 1D one-group diffusion PINN versus identical residual-off MLP."""
import json,time,platform
from pathlib import Path
import numpy as np,pandas as pd
import matplotlib;matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.optimize import least_squares
import scipy
R=Path(__file__).resolve().parents[2]
O=R/"reports/pinn_feasibility_and_experiment_v1"
L=4.0;D=1.0;SIGMA_A=0.5;Q=1.0;HIDDEN=16
SEEDS=(3101,3102,3103,3104,3105)
XOBS=np.array([0.7,2.0,3.3])
XCOL=np.linspace(0.0,L,66)[1:-1]
XVAL=np.linspace(0.0,L,401)
def reference(x):
    k=np.sqrt(SIGMA_A/D)
    return (Q/SIGMA_A)*(1-np.cosh(k*(np.asarray(x)-L/2))/np.cosh(k*L/2))
def unpack(t):
    return t[:HIDDEN],t[HIDDEN:2*HIDDEN],t[2*HIDDEN:3*HIDDEN],t[-1]
def field_and_second(t,x):
    w,b,v,c=unpack(t);u=np.asarray(x)[:,None]*w[None,:]+b[None,:]
    z=np.tanh(u);phi=z@v+c
    d2=(-2*z*(1-z*z)*w[None,:]**2)@v
    return phi,d2
def residual(t,x):
    phi,d2=field_and_second(t,x)
    return -D*d2+SIGMA_A*phi-Q
AMP=float(reference(np.array([L/2]))[0])
def loss_terms(t,physics_weight):
    data=(field_and_second(t,XOBS)[0]-reference(XOBS))/AMP
    bc=field_and_second(t,np.array([0.0,L]))[0]/AMP
    pde=residual(t,XCOL)/Q
    return float(np.mean(data**2)),float(np.mean(bc**2)),float(np.mean(pde**2))
def vector(t,physics_weight):
    data=(field_and_second(t,XOBS)[0]-reference(XOBS))/AMP/np.sqrt(len(XOBS))
    bc=field_and_second(t,np.array([0.0,L]))[0]/AMP/np.sqrt(2)
    pde=np.sqrt(physics_weight)*residual(t,XCOL)/Q/np.sqrt(len(XCOL))
    reg=np.sqrt(1e-6)*t
    return np.r_[data,bc,pde,reg]
def initial(seed):
    g=np.random.default_rng(seed)
    return np.r_[g.normal(0,.45,HIDDEN),g.normal(0,.25,HIDDEN),g.normal(0,.45,HIDDEN),0.0]
def main():
    if O.exists():raise FileExistsError(O)
    O.mkdir(parents=True)
    rows=[];curves=pd.DataFrame({"x_cm":XVAL,"analytic_reference":reference(XVAL)})
    for seed in SEEDS:
        start=initial(seed)
        for name,weight in (("MLP_residual_off",0.0),("PINN_residual_on",1.0)):
            t0=time.perf_counter()
            fit=least_squares(vector,start,args=(weight,),method="trf",max_nfev=550,ftol=1e-10,xtol=1e-10,gtol=1e-10)
            elapsed=time.perf_counter()-t0
            pred=field_and_second(fit.x,XVAL)[0];truth=reference(XVAL)
            err=pred-truth;dr,br,pr=loss_terms(fit.x,weight)
            rows.append({"seed":seed,"method":name,"physics_weight":weight,"data_mse_scaled":dr,"boundary_mse_scaled":br,"physics_residual_mse_scaled":pr,"validation_mae":float(np.mean(np.abs(err))),"validation_rmse":float(np.sqrt(np.mean(err**2))),"validation_relative_l2":float(np.linalg.norm(err)/np.linalg.norm(truth)),"validation_max_abs":float(np.max(np.abs(err))),"validation_pde_residual_rms":float(np.sqrt(np.mean(residual(fit.x,XVAL)**2))),"boundary_max_abs":float(np.max(np.abs(field_and_second(fit.x,np.array([0.,L]))[0]))),"elapsed_seconds":elapsed,"nfev":int(fit.nfev),"optimizer_success":bool(fit.success),"optimizer_message":str(fit.message)})
            curves[name+"_"+str(seed)]=pred
            np.savez_compressed(O/(name+"_"+str(seed)+".npz"),weights=fit.x,seed=seed,physics_weight=weight)
            print(seed,name,"L2",rows[-1]["validation_relative_l2"],"seconds",round(elapsed,2),flush=True)
    metrics=pd.DataFrame(rows);metrics.to_csv(O/"seed_metrics.csv",index=False)
    curves.to_csv(O/"dense_reference_and_predictions.csv",index=False)
    summary=metrics.groupby("method").agg(n=("seed","count"),l2_mean=("validation_relative_l2","mean"),l2_sd=("validation_relative_l2","std"),pde_rms_mean=("validation_pde_residual_rms","mean"),bc_max_mean=("boundary_max_abs","mean"),seconds_mean=("elapsed_seconds","mean"),success_count=("optimizer_success","sum")).reset_index()
    summary.to_csv(O/"method_summary.csv",index=False)
    config={"schema":"controlled_diffusion_pinn_v1","scientific_status":"PROVISIONAL_EXPLORATORY","equation":"-D phi_second + Sigma_a phi = Q","D_cm":D,"Sigma_a_per_cm":SIGMA_A,"Q_arbitrary":Q,"L_cm":L,"boundary":"phi(0)=phi(L)=0 on extrapolated toy slab boundaries","analytic_solution":"Q/Sigma_a*(1-cosh(sqrt(Sigma_a/D)*(x-L/2))/cosh(sqrt(Sigma_a/D)*L/2))","observations_cm":XOBS.tolist(),"collocation_cm":XCOL.tolist(),"validation_grid_count":len(XVAL),"hidden_tanh_units":HIDDEN,"seed_values":list(SEEDS),"optimizer":"scipy least_squares trf; identical initial weights and max_nfev=550","loss_weights":{"data":1.0,"boundary":1.0,"physics_PINN":1.0,"physics_ablation":0.0,"weight_decay":1e-6},"software":{"python":platform.python_version(),"numpy":np.__version__,"scipy":scipy.__version__}}
    (O/"experiment_config.json").write_text(json.dumps(config,indent=2))
    fig,ax=plt.subplots(1,2,figsize=(12,4))
    ax[0].plot(XVAL,reference(XVAL),"k-",linewidth=2,label="analytic")
    for method,color in (("MLP_residual_off","tab:orange"),("PINN_residual_on","tab:blue")):
        for i,seed in enumerate(SEEDS):ax[0].plot(XVAL,curves[method+"_"+str(seed)],color=color,alpha=.4,label=method if i==0 else None)
    ax[0].scatter(XOBS,reference(XOBS),c="k",marker="x",label="3 training observations")
    ax[0].set(xlabel="x (cm)",ylabel="scalar flux (arbitrary)",title="Same 1D diffusion problem");ax[0].legend(fontsize=8)
    for method,color in (("MLP_residual_off","tab:orange"),("PINN_residual_on","tab:blue")):
        part=metrics[metrics.method==method];ax[1].scatter(part.seed,part.validation_relative_l2,c=color,label=method)
    ax[1].set(xlabel="seed",ylabel="dense-grid relative L2",title="Independent initializations");ax[1].legend(fontsize=8)
    fig.tight_layout();fig.savefig(O/"solution_and_seed_stability.png",dpi=160);plt.close(fig)
    fig,ax=plt.subplots(1,3,figsize=(12,3.5))
    for j,(column,title) in enumerate((("data_mse_scaled","Data"),("boundary_mse_scaled","Boundary"),("physics_residual_mse_scaled","Physics residual evaluated"))):
        ax[j].bar(summary.method,metrics.groupby("method")[column].mean().reindex(summary.method));ax[j].set_title(title);ax[j].tick_params(axis="x",labelrotation=15)
    fig.tight_layout();fig.savefig(O/"loss_components.png",dpi=160);plt.close(fig)
    print(summary.to_string(index=False))
if __name__=="__main__":main()
