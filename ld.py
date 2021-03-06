import pdb, sys, os
import numpy as np
import scipy.integrate
import matplotlib.pyplot as plt



def fit_law( grid_mu, grid_wav_nm, grid_intensities, passband_wav_nm, \
             cuton_wav_nm=None, cutoff_wav_nm=None, \
             passband_sensitivity=None, plot_fits=False ):
    """
    Given a stellar model grid, computes the limb darkening coefficients
    for four different limb darkening laws: linear, quadratic, three-parameter
    nonlinear and four-parameter nonlinear.
    """    

    # Make sure the throughput goes to zero at the edges:
    ixs = np.argsort( passband_wav_nm )
    passband_wav_nm = passband_wav_nm[ixs]
    passband_sensitivity = passband_sensitivity[ixs]
    dw = 1e-2
    wl = passband_wav_nm.min()-dw
    wu = passband_wav_nm.max()+dw
    passband_wav_nm = np.concatenate( [ [wl], passband_wav_nm, [wu] ] )
    passband_sensitivity = np.concatenate( [ [0], passband_sensitivity, [0] ] )

    # Restrict stellar model to wavelength range centered on channel:
    dwav = cutoff_wav_nm-cuton_wav_nm
    wavl = cuton_wav_nm - 0.1*dwav
    wavu = cutoff_wav_nm + 0.1*dwav

    ixs = ( grid_wav_nm>=wavl )*( grid_wav_nm<=wavu )

    grid_wav_nm = grid_wav_nm[ixs]
    grid_intensities = grid_intensities[ixs,:]

    # Interpolate onto a finer grid to allow for narrow channels:
    nf = int( 1e6 )
    #xf = np.linspace( grid_wav_nm.min(), grid_wav_nm.max(), nf )
    xf = np.linspace( wavl, wavu, nf )
    nmu = len( grid_mu )
    yf = np.zeros( [ nf, nmu ] )
    for i in range( nmu ):
        yf[:,i] = np.interp( xf, grid_wav_nm, grid_intensities[:,i] )
    grid_wav_nm = xf
    grid_intensities = yf    

    # If no passband transmission function has been provided, use
    # a simple boxcar function:
    if passband_sensitivity is None:
        passband_sensitivity = np.ones( passband_wav_nm.size )

    # Interpolate passband wavelengths onto model wavelength grid:
    ixs = np.argsort( passband_wav_nm )
    passband_wav_nm = passband_wav_nm[ixs]
    passband_sensitivity = passband_sensitivity[ixs]
    passband_sensitivity /= passband_sensitivity.max()

    if plot_fits==True:
        stellar_spec = np.mean( grid_intensities, axis=1 )
        fig = plt.figure( figsize=[10,9] )
        ax1 = fig.add_subplot( 211 )
        ax2 = fig.add_subplot( 212 )
        x1 = grid_wav_nm
        y1 = stellar_spec/stellar_spec.max()
        ax1.plot( x1, y1, '-', c='DodgerBlue', label='Mean Stellar Intensity' )
        ax1.fill_between( passband_wav_nm, np.zeros( passband_sensitivity.size ), \
                          passband_sensitivity, edgecolor='Salmon', facecolor='none', zorder=10, label='Passband' )
        ixs1 = ( y1>0.05*y1.max() )*( x1>x1[np.argmax(y1)] )
        ax1.set_xlim( [ 0, x1[ixs1].max() ] )
        ax1.set_xlabel( 'Wavelength (nm)' )
        ax1.set_ylabel( 'Normalised Flux' )
        ax1.legend( loc='upper right' )

    nwav = len( grid_wav_nm )
    mask = np.zeros( nwav )
    #ixs = ( grid_wav_nm>=passband_wav_nm.min() )*\
    #      ( grid_wav_nm<=passband_wav_nm.max() )
    ixs = ( grid_wav_nm>=cuton_wav_nm )*\
          ( grid_wav_nm<=cutoff_wav_nm )
    mask[ixs] = 1.0

    interp_sensitivity = np.interp( grid_wav_nm, passband_wav_nm, passband_sensitivity )

    # Integrate the model spectra over the passband for each value of mu:
    nmu = len( grid_mu )
    integrated_intensities = np.zeros( nmu )

    x = grid_wav_nm
    y = grid_wav_nm*mask*interp_sensitivity
    nwav = len( grid_wav_nm )
    ixs = np.arange( nwav )[interp_sensitivity>0]
    ixs = np.concatenate( [ [ ixs[0]-1 ], ixs, [ ixs[-1]+1 ] ] )
    ixs = ixs[(ixs>=0)*(ixs<nwav)]
    normfactor = scipy.integrate.simps( y[ixs], x=x[ixs] )
    #normfactor = scipy.integrate.trapz( y[ixs], x=x[ixs] )
    for i in range( nmu ):
        # Multiply the intensities by wavelength to convert
        # from energy flux to photon flux, as appropriate for
        # photon counting devices such as CCDs:
        integrand = grid_wav_nm*mask*interp_sensitivity*grid_intensities[:,i]
        integral = scipy.integrate.simps( integrand, x=grid_wav_nm )
        #integral = scipy.integrate.trapz( integrand, x=grid_wav_nm )
        integrated_intensities[i] = integral/normfactor
    integrated_intensities /= integrated_intensities[0]

    # Evaluate limb darkening coefficients using linear least
    # squares for each of the four limb darkening laws:
    ld_coeff_fits = {}
    laws = [ fourparam_nonlin_ld, threeparam_nonlin_ld, quadratic_ld, linear_ld ]
    if plot_fits==True:
        ax2.plot( grid_mu, integrated_intensities, 'ok' )
        cs = [ 'PaleGreen', 'ForestGreen', 'Indigo', 'Orange' ]
    n = len( laws )
    for i in range( n ):
        name, phi = laws[i]( grid_mu, coeffs=None )
        # Following Sing (2010), exclude certain values
        # of mu, depending on the limb darkening law:
        if name=='fourparam_nonlin':
            ixs = ( grid_mu>=0 )
        else:
            ixs = ( grid_mu>=0.05 )
        coeffs = np.linalg.lstsq( phi[ixs,:], integrated_intensities[ixs]-1 )[0]
        ld_coeff_fits[name] = coeffs
        if plot_fits==True:
            ax2.plot( grid_mu[ixs], 1+np.dot( phi[ixs,:], coeffs ), '-', c=cs[i], lw=2, label=name )
    if plot_fits==True:
        ax2.legend( loc='upper left' )
        ax2.set_ylabel( 'Passband-integrated Intensity' )
        ax2.set_xlabel( 'mu=cos(theta)' )

    return ld_coeff_fits


def linear_ld( mus, coeffs=None ):
    """
    Linear limb darkening law.

    I(mu) = c0 - c1*( 1-mu )

    Note, that if coeffs==None, then the basis
    matrix will be returned in preparation for
    finding the limb darkening coeffecients by
    linear least squares. Otherwise, coeffs
    should be an array with 1 entries, one for
    each of the linear limb darkening
    coefficients, in which case the output will
    be the limb darkening law evaluated with
    those coefficients at the locations of the
    mus entries.
    """

    if coeffs is None:
        phi = np.ones( [ len( mus ), 1 ] )
        phi[:,0] = -( 1.0 - mus )

    else:
        phi = 1. - coeffs[1]*( 1.0 - mus )

    return 'linear', phi


def quadratic_ld( mus, coeffs=None ):
    """
    Quadratic limb darkening law.

    I(mu) = c0 - c1*( 1-mu ) - c2*( ( 1-mu )**2. )

    Note, that if coeffs==None, then the basis
    matrix will be returned in preparation for
    finding the limb darkening coeffecients by
    linear least squares. Otherwise, coeffs
    should be an array with 2 entries, one for
    each of the quadratic limb darkening
    coefficients, in which case the output will
    be the limb darkening law evaluated with
    those coefficients at the locations of the
    mus entries.
    """

    if coeffs is None:
        phi = np.ones( [ len( mus ), 2 ] )
        phi[:,0] = -( 1.0 - mus )
        phi[:,1] = -( ( 1.0 - mus )**2. )

    else:
        phi = 1. - coeffs[0]*( 1.0 - mus ) \
              - coeffs[1]*( ( 1.0 - mus )**2. )

    return 'quadratic', phi


def threeparam_nonlin_ld( mus, coeffs=None ):
    """
    The nonlinear limb darkening law as defined
    in Sing 2010.

    Note, that if coeffs==None, then the basis
    matrix will be returned in preparation for
    finding the limb darkening coeffecients by
    linear least squares. Otherwise, coeffs
    should be an array with 4 entries, one for
    each of the nonlinear limb darkening
    coefficients, in which case the output will
    be the limb darkening law evaluated with
    those coefficients at the locations of the
    mus entries.
    """

    if coeffs is None:
        phi = np.ones( [ len( mus ), 3 ] )
        phi[:,0] = - ( 1.0 - mus )
        phi[:,1] = - ( 1.0 - mus**(3./2.) )
        phi[:,2] = - ( 1.0 - mus**2. )

    else:
        phi = 1 - coeffs[0] * ( 1.0 - mus ) \
              - coeffs[1] * ( 1.0 - mus**(3./2.) ) \
              - coeffs[2] * ( 1.0 - mus**2. )

    return 'threeparam_nonlin', phi


def fourparam_nonlin_ld( mus, coeffs=None ):
    """
    The nonlinear limb darkening law as defined
    in Equation 5 of Claret et al 2004.

    Note, that if coeffs==None, then the basis
    matrix will be returned in preparation for
    finding the limb darkening coeffecients by
    linear least squares. Otherwise, coeffs
    should be an array with 4 entries, one for
    each of the nonlinear limb darkening
    coefficients, in which case the output will
    be the limb darkening law evaluated with
    those coefficients at the locations of the
    mus entries.
    """

    if coeffs is None:
        phi = np.ones( [ len( mus ), 4 ] )
        phi[:,0] = - ( 1.0 - mus**(1./2.) )
        phi[:,1] = - ( 1.0 - mus )
        phi[:,2] = - ( 1.0 - mus**(3./2.) )
        phi[:,3] = - ( 1.0 - mus**(2.) )

    else:
        phi = 1 - coeffs[0] * ( 1.0 - mus**(1./2.) ) \
              - coeffs[1] * ( 1.0 - mus ) \
              - coeffs[2] * ( 1.0 - mus**(3./2.) ) \
              - coeffs[3] * ( 1.0 - mus**(2.) )

    return 'fourparam_nonlin', phi


