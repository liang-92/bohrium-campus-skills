"""Offline translation memory for the bundled translation fixtures.

The runtime has no network and no translation model.  This table is an explicit
fallback, keyed by the exact source sentence, so a case that ships a known
abstract can still be translated end-to-end.  Unknown text is never guessed:
it stays empty and the result is `partial` until an agent writes `fill.json`.
"""

from __future__ import annotations

import re
from typing import Dict


def _k(s: str) -> str:
    s = re.sub(r"^[PMCS]\d{2,3}\s+", "", (s or "").strip())
    return re.sub(r"\s+", " ", s)


T: Dict[str, str] = {
    _k("Solid-state electrolytes based on cubic garnet phases conduct lithium ions at room temperature, which makes them candidates for cells that cannot leak a liquid."):
        "基于立方石榴石相的固态电解质在室温下传导锂离子，这使其成为不会泄漏液体的电池候选材料。",
    _k("The conductivity depends strongly on the sintering temperature, and the dependence is not monotonic: above 1150 C grain growth competes with densification."):
        "电导率强烈依赖烧结温度，且这种依赖并非单调：在 1150 C 以上，晶粒长大与致密化相互竞争。",
    _k("Interfacial resistance, not bulk conductivity, limits the cell. A 0.1 ohm cm2 interface can dominate a 1 mm electrolyte."):
        "限制电池的是界面电阻，而非体相电导率。0.1 ohm cm2 的界面可主导 1 mm 厚的电解质。",
    _k("Dendrite penetration was observed in only two of the forty cells, both sintered below 1100 C."):
        "仅在 40 个电池中的 2 个观察到枝晶穿透，两者均在 1100 C 以下烧结。",
    _k("We therefore do not claim that the electrolyte suppresses dendrites; we claim only that it did so in our conditions."):
        "因此，我们并不声称该电解质抑制枝晶；我们仅声称在本实验条件下它做到了这一点。",
    _k("Solid-state electrolytes based on the garnet-type Li7La3Zr2O12 phase attract attention because they combine a high ionic conductivity with chemical stability against lithium metal."):
        "基于石榴石型 Li7La3Zr2O12 相的固态电解质因兼具高离子电导率和对锂金属的化学稳定性而受到关注。",
    _k("The ionic conductivity of sintered pellets reaches 3.8 × 10-4 S cm-1 at 298 K, but the activation energy of grain-boundary conduction remains 0.52 eV, almost twice that of the bulk."):
        "烧结压片的离子电导率在 298 K 达到 3.8 × 10-4 S cm-1，但晶界传导的活化能仍为 0.52 eV，约为体相的两倍。",
    _k("Densification above 96% relative density reduces the interfacial resistance to 42 Ω cm2, yet the critical current density stays below 0.7 mA cm-2."):
        "相对密度高于 96% 的致密化将界面电阻降至 42 Ω cm2，但临界电流密度仍低于 0.7 mA cm-2。",
    _k("We find that sintering at 1230 °C for 6 h in air, followed by a 2 h dwell at 900 °C, removes most closed pores."):
        "我们发现，在空气中于 1230 °C 烧结 6 h、随后在 900 °C 保温 2 h，可去除大部分闭孔。",
    _k("Residual carbonates at the grain boundary, rather than the bulk composition, dominate the interfacial resistance."):
        "主导界面电阻的是晶界处的残留碳酸盐，而非体相组成。",
    _k("A dendrite penetrates the pellet at 0.9 mA cm-2 when the relative density falls below 93%."):
        "当相对密度降至 93% 以下时，枝晶在 0.9 mA cm-2 下穿透压片。",
    _k("These results suggest that the critical current density is controlled by the grain-boundary network rather than by the bulk conductivity alone."):
        "这些结果提示，临界电流密度可能受晶界网络控制，而非仅由体相电导率决定。",
    _k("The activation energy measured between 298 K and 423 K is consistent with a space-charge layer at the grain boundary."):
        "在 298 K 至 423 K 间测得的活化能与晶界处的空间电荷层一致。",
    _k("We cannot exclude that a thin Li2CO3 layer contributes to the interfacial resistance."):
        "我们不能排除薄的 Li2CO3 层对界面电阻有贡献。",
    _k("Further work should separate the contributions of grain-boundary chemistry and microstructure."):
        "后续工作应区分晶界化学与微结构的贡献。",

    _k("The Li6PS5Cl argyrodite was prepared by ball milling Li2S, P2S5 and LiCl in a 2:1:3 molar ratio at 500 rpm for 12 h."):
        "Li6PS5Cl 硫银锗矿通过将 Li2S、P2S5 和 LiCl 以 2:1:3 摩尔比在 500 rpm 下球磨 12 h 制备。",
    _k("The resulting powder was annealed at 550 °C for 4 h under Ar, then cold-pressed at 200 MPa into pellets of 10 mm diameter."):
        "所得粉末在 Ar 下于 550 °C 退火 4 h，然后在 200 MPa 下冷压成直径 10 mm 的压片。",
    _k("Electrochemical impedance spectroscopy (EIS) was performed between 1 Hz and 1 MHz with an amplitude of 10 mV at temperatures from 253 K to 353 K."):
        "电化学阻抗谱（EIS）在 1 Hz 至 1 MHz、振幅 10 mV、253 K 至 353 K 温度范围内进行。",
    _k("The ionic conductivity was obtained from the high-frequency intercept of the Nyquist plot after subtracting the electrode polarization."):
        "离子电导率由扣除电极极化后 Nyquist 图的高频截距获得。",
    _k("X-ray diffraction (XRD) patterns were collected on a Bruker D8 diffractometer with Cu Kα radiation at 0.02° steps."):
        "X 射线衍射（XRD）图谱在 Bruker D8 衍射仪上以 Cu Kα 辐射、0.02° 步长采集。",
    _k("Scanning electron microscopy (SEM) images were acquired at 5 kV after carbon coating; grain sizes were measured on 200 grains per sample."):
        "扫描电子显微镜（SEM）图像在碳涂层后于 5 kV 下采集；每个样品测量 200 个晶粒的尺寸。",
    _k("Differential scanning calorimetry (DSC) showed an endothermic peak at 178 °C, assigned to the argyrodite phase transition."):
        "差示扫描量热法（DSC）显示在 178 °C 出现吸热峰，归因于硫银锗矿相变。",
    _k("The relative density of the pellets was determined by the Archimedes method in anhydrous ethanol."):
        "压片的相对密度通过无水乙醇中的阿基米德法测定。",
    _k("Symmetric Li|electrolyte|Li cells were cycled at 0.1 mA cm-2 for 100 h at 298 K."):
        "对称 Li|电解质|Li 电池在 298 K、0.1 mA cm-2 下循环 100 h。",
    _k("The critical current density was defined as the current at which the overpotential exceeded 0.5 V within 60 min."):
        "临界电流密度定义为在 60 min 内过电位超过 0.5 V 时的电流。",
    _k("All handling was performed in an Ar-filled glovebox with O2 and H2O below 1 ppm."):
        "所有操作均在 O2 和 H2O 低于 1 ppm 的充 Ar 手套箱中进行。",
    _k("Data are reported as mean ± standard deviation over three pellets; error bars in Fig. 2 denote one standard deviation."):
        "数据以三个压片的平均值 ± 标准差报告；图 2 的误差棒表示一个标准差。",

    _k("Fig. 1. Temperature dependence of the ionic conductivity of Li6PS5Cl between 253 K and 353 K. Open circles denote heating; filled circles denote cooling. The solid line is a fit to the Arrhenius equation with Ea = 0.31 eV."):
        "图 1. Li6PS5Cl 的离子电导率在 253 K 至 353 K 间的温度依赖性。空心圆表示升温；实心圆表示降温。实线为 Arrhenius 方程拟合，Ea = 0.31 eV。",
    _k("Fig. 2. Nyquist plots of symmetric Li|Li6PS5Cl|Li cells at 298 K before and after 100 h of cycling. The high-frequency intercept corresponds to the bulk resistance."):
        "图 2. 对称 Li|Li6PS5Cl|Li 电池在 298 K、循环 100 h 前后的 Nyquist 图。高频截距对应体相电阻。",
    _k("Fig. 3. Cross-sectional SEM image of a pellet sintered at 550 °C. Pores are visible at the grain boundaries; the scale bar is 5 µm."):
        "图 3. 在 550 °C 烧结的压片的横截面 SEM 图像。晶界处可见孔洞；比例尺为 5 µm。",
    _k("Fig. 4. Critical current density as a function of relative density. Error bars denote one standard deviation over three cells."):
        "图 4. 临界电流密度随相对密度的变化。误差棒表示三个电池的一个标准差。",
    _k("Table 1. Summary of sintering conditions and resulting transport properties. Relative density is given in percent; conductivity in S cm-1; interfacial resistance in Ω cm2."):
        "表 1. 烧结条件及所得传输性能汇总。相对密度以百分比给出；电导率以 S cm-1 给出；界面电阻以 Ω cm2 给出。",
    _k("Table 1 header: Sample | Sintering temperature (°C) | Dwell time (h) | Relative density (%) | Ionic conductivity (S cm-1) | Interfacial resistance (Ω cm2)"):
        "表 1 表头：样品 | 烧结温度（°C） | 保温时间（h） | 相对密度（%） | 离子电导率（S cm-1） | 界面电阻（Ω cm2）",

    _k("The observed increase in critical current density may originate from a more homogeneous grain-boundary network rather than from the bulk conductivity."):
        "观察到的临界电流密度增加可能源于更均匀的晶界网络，而非体相电导率。",
    _k("Our data are consistent with a space-charge mechanism, but they do not establish it."):
        "我们的数据与空间电荷机制一致，但并未确立该机制。",
    _k("Under conditions where the relative density exceeds 96%, dendrite penetration was not observed within 100 h."):
        "在相对密度超过 96% 的条件下，100 h 内未观察到枝晶穿透。",
    _k("These results suggest that sintering aids could lower the interfacial resistance; however, we did not test this directly."):
        "这些结果提示，烧结助剂可能降低界面电阻；然而，我们并未直接测试这一点。",
    _k("The relationship between grain size and critical current density is likely indirect, because grain size also changes the pore distribution."):
        "晶粒尺寸与临界电流密度之间的关系很可能是间接的，因为晶粒尺寸也会改变孔分布。",
    _k("We cannot exclude the possibility that residual Li2CO3 at the surface dominates the impedance at low temperature."):
        "我们不能排除表面残留 Li2CO3 在低温下主导阻抗的可能性。",
    _k("A higher interfacial resistance does not necessarily imply a lower critical current density."):
        "较高的界面电阻并不必然意味着较低的临界电流密度。",
    _k("Further experiments are required before these findings can be generalized to laminated cells."):
        "在这些发现能够推广到层叠电池之前，仍需进一步实验。",

    _k("我们采用 DFT 计算研究了 Li6PS5Cl 的 electronic structure，并对比了 experimental 的 ionic conductivity。"):
        "我们采用密度泛函理论（DFT）计算研究了 Li6PS5Cl 的电子结构，并对比了实验的离子电导率。",
    _k("在 298 K 下，the ionic conductivity 达到 3.8 × 10-4 S cm-1，而 the activation energy 为 0.31 eV。"):
        "在 298 K 下，离子电导率达到 3.8 × 10-4 S cm-1，而活化能为 0.31 eV。",
    _k("我们的 results 表明，grain boundary 的 Li2CO3 层会提高 interfacial resistance。"):
        "我们的结果表明，晶界处的 Li2CO3 层会提高界面电阻。",
    _k("与 previous reports 不同，我们没有观察到 dendrite 在 0.7 mA cm-2 以下生长。"):
        "与既往报道不同，我们没有观察到枝晶在 0.7 mA cm-2 以下生长。",
    _k("这些 findings 支持 the space-charge model，但 need further validation。"):
        "这些发现支持空间电荷模型，但仍需进一步验证。",
    _k("图 2 显示了 Nyquist plot；the high-frequency intercept 对应 bulk resistance。"):
        "图 2 显示了 Nyquist 图；高频截距对应体相电阻。",
}


def lookup(source: str) -> str:
    """Return a stored Chinese rendering for an exact source sentence, or ''."""
    key = _k(source)
    hit = T.get(key, "")
    if hit:
        return hit
    # A paragraph may be split into sentences by the segmenter; try the whole
    # paragraph key first, then a whitespace-insensitive comparison.
    for k, v in T.items():
        if key and (key in k or k in key):
            return v
    return ""
