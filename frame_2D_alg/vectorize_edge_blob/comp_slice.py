import numpy as np
from itertools import zip_longest
from copy import copy, deepcopy
from .classes import CderP, CPP
from .filters import ave, aves, vaves, PP_vars, ave_dangle, ave_daangle,med_decay, aveB

'''
comp_slice traces edge blob axis by cross-comparing vertically adjacent Ps: slices across edge blob, along P.G angle.
These low-M high-Ma blobs are vectorized into outlines of adjacent flat (high internal match) blobs.
(high match or match of angle: M | Ma, roughly corresponds to low gradient: G | Ga)
'''

def comp_slice(blob, verbose=False):  # high-G, smooth-angle blob, composite dert core param is v_g + iv_ga

    P__ = blob.P__
    _P_ = P__[0]  # higher row
    for P_ in P__[1:]:  # lower row
        for P in P_:
            link_,link_m,link_d = [],[],[]  # empty in initial Ps
            Valt = [0,0]; Rdnt = [0,0]
            DerH = [[[],[]]]
            for _P in _P_:
                _L = len(_P.dert_); L = len(P.dert_); _x0=_P.box[2]; x0=P.box[2]
                # test for x overlap(_P,P) in 8 directions, all derts positive:
                if (x0 - 1 < _x0 + _L) and (x0 + L > _x0):
                    comp_P(_P,P, link_,link_m,link_d, Valt, Rdnt, DerH, fd=0)
                elif (x0 + L) < _x0:
                    break  # no xn overlap, stop scanning lower P_
            if link_:
                P.derH=[DerH]  # single [Mtuple, Dtuple] here
                P.link_=link_; P.link_t=[link_m,link_d]; P.valt=Valt; P.rdnt=Rdnt
        _P_ = P_
    PPm_,PPd_ = form_PP_t(P__, base_rdn=2)
    blob.PPm_, blob.PPd_  = PPm_, PPd_


def form_PP_t(P__, base_rdn):  # form PPs of derP.valt[fd] + connected Ps'val

    PP_t = []
    for fd in 0, 1:
        fork_P__ = ([copy(P_) for P_ in reversed(P__)])  # scan bottom-up
        PP_ = []; packed_P_ = []  # form initial sequence-PPs:
        for P_ in fork_P__:
            for P in P_:
                if P not in packed_P_:
                    qPP = [[[P]], P.valt[fd]]  # init PP is 2D queue of node Ps and sum([P.val+P.link_val])
                    uplink_ = P.link_t[fd]; uuplink_ = []  # next-line links for recursive search
                    while uplink_:
                        for derP in uplink_:
                            if derP._P not in packed_P_:
                                qPP[0].insert(0, [derP._P])  # pack top down
                                qPP[1] += derP.valt[fd]
                                packed_P_ += [derP._P]
                                uuplink_ += derP._P.link_t[fd]
                        uplink_ = uuplink_
                        uuplink_ = []
                    PP_ += [qPP + [ave+1]]  # + [ini reval]
        # prune qPPs by med links val:
        rePP_= reval_PP_(PP_, fd)  # PP = [qPP,val,reval]
        CPP_ = [sum2PP(PP, base_rdn, fd) for PP in rePP_]
        PP_t += [CPP_]  # may be empty

    return PP_t  # add_alt_PPs_(graph_t)?

def reval_PP_(PP_, fd):  # recursive eval / prune Ps for rePP

    rePP_ = []
    while PP_:  # init P__
        P__, val, reval = PP_.pop(0)
        if val > ave:
            if reval < ave:  # same graph, skip re-evaluation:
                rePP_ += [[P__,val,0]]  # reval=0
            else:
                rePP = reval_P_(P__, fd)  # recursive node and link revaluation by med val
                if rePP[1] > ave:  # min adjusted val
                    rePP_ += [rePP]
    if rePP_ and max([rePP[2] for rePP in rePP_]) > ave:  # recursion if any min reval:
        rePP_ = reval_PP_(rePP_, fd)

    return rePP_

def reval_P_(P__, fd):  # prune qPP by (link_ + mediated link__) val

    prune_ = []; Val, reval = 0,0  # comb PP value and recursion value

    for P_ in P__:
        for P in P_:
            P_val = 0; remove_ = []
            for link in P.link_t[fd]:
                # recursive mediated link layers eval-> med_valH:
                _,_,med_valH = med_eval(link._P.link_t[fd], old_link_=[], med_valH=[], fd=fd)
                # link val + mlinks val: single med order, no med_valH in comp_slice?:
                link_val = link.valt[fd] + sum([mlink.valt[fd] for mlink in link._P.link_t[fd]]) * med_decay  # + med_valH
                if link_val < vaves[fd]:
                    remove_+= [link]; reval += link_val
                else: P_val += link_val
            for link in remove_:
                P.link_t[fd].remove(link)  # prune weak links
            if P_val < vaves[fd]:
                prune_ += [P]
            else:
                Val += P_val
    for P in prune_:
        for link in P.link_t[fd]:  # prune direct links only?
            _P = link._P
            _link_ = _P.link_t[fd]
            if link in _link_:
                _link_.remove(link); reval += link.valt[fd]

    if reval > aveB:
        P__, Val, reval = reval_P_(P__, fd)  # recursion
    return [P__, Val, reval]

def med_eval(last_link_, old_link_, med_valH, fd):  # compute med_valH

    curr_link_ = []; med_val = 0

    for llink in last_link_:
        for _link in llink._P.link_t[fd]:
            if _link not in old_link_:  # not-circular link
                old_link_ += [_link]  # evaluated mediated links
                curr_link_ += [_link]  # current link layer,-> last_link_ in recursion
                med_val += _link.valt[fd]
    med_val *= med_decay ** (len(med_valH) + 1)
    med_valH += [med_val]
    if med_val > aveB:
        # last med layer val-> likely next med layer val
        curr_link_, old_link_, med_valH = med_eval(curr_link_, old_link_, med_valH, fd)  # eval next med layer

    return curr_link_, old_link_, med_valH


def sum2PP(qPP, base_rdn, fd):  # sum Ps and links into PP

    P__, val, _ = qPP  # proto-PP is a list
    # init:
    P0 = P__[0][0]
    PP = CPP(box=copy(P0.box), fds=[fd], P__ = P__)
    PP.valt[fd] = val; PP.rdnt[fd] += base_rdn
    # accum:
    for P_ in P__:  # top-down
        for P in P_:  # left-to-right
            P.roott[fd] = PP
            sum_ptuple(PP.ptuple, P.ptuple)
            sum_derH(PP.derH, P.derH)
            PP.link_ += P.link_
            for Link_,link_ in zip(PP.link_t, P.link_t):
                Link_ += link_  # all unique links in PP, to replace n
            Y0,Yn,X0,Xn = PP.box; y0,yn,x0,xn = P.box
            PP.box = [min(Y0,y0), max(Yn,yn), min(X0,x0), max(Xn,xn)]

    return PP


def sum_derH(DerH, derH, fd=2):  # derH is layers, not selective here. Sum mtuple is for future param select

    for Layer, layer in zip_longest(DerH, derH, fillvalue=None):
        if layer != None:
            if Layer != None:
                sum_layer(Layer, layer, fd=2)
            else:
                DerH += [deepcopy(layer)]

def sum_layer(Layer, layer, fd=2):

    for Vertuple, vertuple in zip_longest(Layer, layer, fillvalue=None):  # vertuple is [mtuple, dtuple]
        if vertuple != None:
            if Vertuple != None:
                if fd==2: sum_vertuple(Vertuple, vertuple)  # not fork-selective
                else: sum_tuple(Vertuple[fd], vertuple[fd])
            else:
                Layer += [deepcopy(vertuple)]


def sum_vertuple(Vertuple, vertuple):  # [mtuple,dtuple]

    for Ptuple, ptuple in zip_longest(Vertuple, vertuple, fillvalue=None):
        if ptuple != None:
            if Ptuple != None:
                sum_tuple(Ptuple, ptuple)
            else:
                Vertuple += deepcopy(vertuple)

def sum_tuple(Ptuple,ptuple, fneg=0):  # mtuple or dtuple

    for i, (Par, par) in enumerate(zip_longest(Ptuple, ptuple, fillvalue=None)):
        if par != None:
            if Par != None:
                Ptuple[i] = Par + -par if fneg else par
            elif not fneg:
                Ptuple += [par]

def sum_ptuple(Ptuple, ptuple, fneg=0):

    for pname, ave in zip(PP_vars, aves):
        Par = getattr(Ptuple, pname); par = getattr(ptuple, pname)

        if isinstance(Par, list):  # angle or aangle
            for j, (P,p) in enumerate(zip(Par,par)): Par[j] = P-p if fneg else P+p
        else:
            Par += (-par if fneg else par)
        setattr(Ptuple, pname, Par)

    Ptuple.n += 1  # not needed?


def comp_P(_P,P, link_,link_m,link_d, Valt, Rdnt, DerH, fd=0, derP=None, DerLay=None):  #  last two if der+

    # compare last layer only, lower layers of _P,P have already been compared forming derP.derH
    if fd:
        # der+: extend old link
        derLay=[]  # new derP layer
        Mval,Dval, Mrdn,Drdn = 0,0,0,0
        # compare last Lay of any length:
        for i, (_vertuple, vertuple) in enumerate(zip_longest(_P.derH[-1], P.derH[-1])):
            mtuple, dtuple = comp_dtuple(_vertuple[1], vertuple[1], rn = len(_P.link_t[1])/len(P.link_t[1]))
            if DerLay:
                sum_tuple(DerLay[i][0],mtuple); sum_tuple(DerLay[i][1],dtuple)
            else:
                DerLay += [[deepcopy(mtuple), deepcopy(dtuple)]]
            derLay += [[mtuple, dtuple]]
            mval = sum(dtuple); dval = sum(dtuple)
            mrdn = 1+(dval>mval); drdn = 1+(1-mrdn)  # define per par?
            Mval+=mval; Dval+=dval
            Mrdn+=mrdn; Drdn+=drdn
        derP.fds+=[fd]; derP.valt[0]+=Mval; derP.valt[1]+=Dval; derP.rdnt[0]+=Mrdn; derP.rdnt[1]+=Drdn
    else:
        # rng+: add new link
        mtuple,dtuple = comp_ptuple(_P.ptuple, P.ptuple)
        Mval = sum(mtuple); Dval = sum(dtuple)
        Mrdn = 1+(Dval>Mval); Drdn = 1+(1-Mrdn)
        # replace with greyscale rdn: Dval/Mval?
        derP = CderP(derH=[[[mtuple,dtuple]]], fds=P.fds+[fd], valt=[Mval,Dval],rdnt=[Mrdn,Drdn], P=P,_P=_P,
                     box=copy(_P.box),L=len(_P.dert_))  # or recompute box from means?
    link_ += [derP]  # all links
    if Mval > aveB*Mrdn:
        link_m+=[derP]; Valt[0]+=Mval; Rdnt[0]+=Mrdn  # +ve links, fork selection in form_PP_t
        if fd: sum_derH(DerH, derP.derH, fd=0)  # sum fork of old layers
        else: sum_tuple(DerH[0][0], mtuple)
    if Dval > aveB*Drdn:
        link_d+=[derP]; Valt[1]+=Dval; Rdnt[1]+=Drdn
        if fd: sum_derH(DerH, derP.derH, fd=1)
        else: sum_tuple(DerH[0][1], dtuple)

    if fd: derP.derH += [derLay]  # DerH must be summed above with old derP.derH


def comp_dtuple(_ituple, ituple, rn):

    mtuple, dtuple = [],[]
    for _par, par, ave in zip(_ituple, ituple, aves):  # compare ds only?

        m,d = comp_par(_par, par*rn, ave)
        mtuple+=[m]; dtuple+=[d]

    return [mtuple, dtuple]

def comp_ptuple(_ptuple, ptuple):

    mtuple, dtuple = [],[]  # in the order of ("I", "M", "Ma", "angle", "aangle","G", "Ga", "x", "L")
    rn = _ptuple.n / ptuple.n  # normalize param as param*rn for n-invariant ratio: _param / param*rn = (_param/_n) / (param/n)

    for pname, ave in zip(PP_vars, aves):
        _par = getattr(_ptuple, pname)
        par = getattr(ptuple, pname)
        if pname=="aangle": m,d = comp_aangle(_par, par)
        elif pname == "angle": m,d = comp_angle(_par, par)
        else:
            if pname!="x": par*=rn  # normalize by relative accum count
            if pname=="x" or pname=="I": finv = 1
            else: finv=0
            m,d = comp_par(_par, par, ave, finv)
        mtuple += [m]
        dtuple += [d]

    return [mtuple, dtuple]

def comp_par(_param, param, ave, finv=0):  # comparand is always par or d in [m,d]

    d = _param - param
    if finv: m = ave - abs(d)  # inverse match for primary params, no mag/value correlation
    else:    m = min(_param, param) - ave
    return [m,d]

def comp_angle(_angle, angle):  # rn doesn't matter for angles

    _Dy, _Dx = _angle
    Dy, Dx = angle
    _G = np.hypot(_Dy,_Dx); G = np.hypot(Dy,Dx)
    sin = Dy / (.1 if G == 0 else G);     cos = Dx / (.1 if G == 0 else G)
    _sin = _Dy / (.1 if _G == 0 else _G); _cos = _Dx / (.1 if _G == 0 else _G)
    sin_da = (cos * _sin) - (sin * _cos)  # sin(α - β) = sin α cos β - cos α sin β
    # cos_da = (cos * _cos) + (sin * _sin)  # cos(α - β) = cos α cos β + sin α sin β
    dangle = sin_da
    mangle = ave_dangle - abs(dangle)  # inverse match, not redundant as summed across sign

    return [mangle, dangle]

def comp_aangle(_aangle, aangle):

    _sin_da0, _cos_da0, _sin_da1, _cos_da1 = _aangle
    sin_da0, cos_da0, sin_da1, cos_da1 = aangle

    sin_dda0 = (cos_da0 * _sin_da0) - (sin_da0 * _cos_da0)
    cos_dda0 = (cos_da0 * _cos_da0) + (sin_da0 * _sin_da0)
    sin_dda1 = (cos_da1 * _sin_da1) - (sin_da1 * _cos_da1)
    cos_dda1 = (cos_da1 * _cos_da1) + (sin_da1 * _sin_da1)
    # for 2D, not reduction to 1D:
    # aaangle = (sin_dda0, cos_dda0, sin_dda1, cos_dda1)
    # day = [-sin_dda0 - sin_dda1, cos_dda0 + cos_dda1]
    # dax = [-sin_dda0 + sin_dda1, cos_dda0 + cos_dda1]
    gay = np.arctan2((-sin_dda0 - sin_dda1), (cos_dda0 + cos_dda1))  # gradient of angle in y?
    gax = np.arctan2((-sin_dda0 + sin_dda1), (cos_dda0 + cos_dda1))  # gradient of angle in x?

    # daangle = sin_dda0 + sin_dda1?
    daangle = np.arctan2(gay, gax)  # diff between aangles, probably wrong
    maangle = ave_daangle - abs(daangle)  # inverse match, not redundant as summed

    return [maangle,daangle]