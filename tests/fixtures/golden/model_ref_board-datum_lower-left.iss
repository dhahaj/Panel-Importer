<?xml version="1.0" encoding="utf-8"?>
<productionProgram>
  <headerData>
    <targetMachine>ISS</targetMachine>
    <editMachine>ISS</editMachine>
    <lastEdit>2026-11-05T09:30:00-06:00</lastEdit>
    <lineConfiguration>
      <lineName id="1">Line</lineName>
    </lineConfiguration>
    <headPwb total="1" completion="1" />
    <headPlacement total="2" completion="0" />
    <headComponent total="2" completion="0" />
  </headerData>
  <core>
    <pwbData>
      <pwbId>T</pwbId>
      <pwbBasic>
        <referenceSide>FRONT</referenceSide>
        <transferDirection>LTOR</transferDirection>
        <referenceType>SHAPE</referenceType>
        <circuitType>STANDARD</circuitType>
        <bocMarkSelect>ALL</bocMarkSelect>
        <markRecognition>GRAYSCALE</markRecognition>
        <badMarkType>STANDARD</badMarkType>
        <badMarkRecognition>POSITIVE</badMarkRecognition>
      </pwbBasic>
      <pwbConfiguration>
        <outline x="100" y="120" />
        <pwbThick thick="1.6" />
        <backHeight height="37" />
        <pwbHeight height="0" />
      </pwbConfiguration>
      <circuitConfigurationData>
        <circuitConfiguration index="0">
          <circuitUse>USE</circuitUse>
          <circuitId>A</circuitId>
          <circuitConfiguration>NONMATRIX</circuitConfiguration>
          <bocMarkType>PWBBOC</bocMarkType>
          <circuitOutline x="40" y="50" />
          <referencePosition />
          <nonMatrix>
            <totalCount count="4" />
            <allocation index="0" x="0" y="0" angle="0" rangeOver="0" />
            <allocation index="1" x="45" y="0" angle="0" rangeOver="0" />
            <allocation index="2" x="0" y="55" angle="0" rangeOver="0" />
            <allocation index="3" x="45" y="55" angle="0" rangeOver="0" />
          </nonMatrix>
        </circuitConfiguration>
        <circuitConfiguration index="1">
          <circuitUse>NOUSE</circuitUse>
          <circuitId>B</circuitId>
          <circuitConfiguration>SINGLE</circuitConfiguration>
          <bocMarkType>NOUSE</bocMarkType>
          <circuitOutline />
          <referencePosition />
        </circuitConfiguration>
      </circuitConfigurationData>
    </pwbData>
    <placementData>
      <placement index="0">
        <placementId>R1</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>P-1</componentName>
        <placementPosition x="-30" y="-30" rangeOver="False" />
        <placementAngle angle="30" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
      <placement index="1">
        <placementId>C1</placementId>
        <baseCircuitId>A</baseCircuitId>
        <componentName>P-2</componentName>
        <placementPosition x="-4.5" y="-47.75" rangeOver="False" />
        <placementAngle angle="90" />
        <attribute>
          <skip placement="NO" adhesive="NO" />
        </attribute>
      </placement>
    </placementData>
    <componentData>
      <component index="0">
        <componentBasic>
          <componentName>P-1</componentName>
          <comment>Description of R1</comment>
          <componentSize witdh="1.6" length="0.8" height="0.55" />
          <connecterHeight height="0" />
        </componentBasic>
      </component>
      <component index="1">
        <componentBasic>
          <componentName>P-2</componentName>
          <comment>Description of C1</comment>
          <componentSize witdh="1.6" length="0.8" height="0.55" />
          <connecterHeight height="0" />
        </componentBasic>
      </component>
    </componentData>
  </core>
  <model>
    <pwbData>
      <pwbId>T</pwbId>
      <pwbBasic>
        <pwbMaterial>EPOXY</pwbMaterial>
        <vacuumTable>NOUSE</vacuumTable>
        <traceability>TwoDimensions</traceability>
      </pwbBasic>
      <pwbConfiguration>
        <pwbLayoutOffset x="55" y="-55" />
        <referencePosition x="0" y="0" />
        <clampOffset y="60" />
      </pwbConfiguration>
      <circuitConfigurationData>
        <circuitConfiguration index="0">
          <circuitId>A</circuitId>
          <circuitLayoutOffset x="-40" y="-50" />
        </circuitConfiguration>
        <circuitConfiguration index="1">
          <circuitId>B</circuitId>
          <circuitLayoutOffset x="0" y="0" />
        </circuitConfiguration>
      </circuitConfigurationData>
    </pwbData>
    <placementData>
      <placement index="0">
        <placementId>R1</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
      <placement index="1">
        <placementId>C1</placementId>
        <attribute>
          <action placement="Place" adhesive="NoAdhesive" />
        </attribute>
      </placement>
    </placementData>
  </model>
  <machine>
    <bocMarkData>
      <circuitData index="0">
        <bocMark no="1">
          <markType>BOC</markType>
          <markName>BOCMARK01</markName>
          <solderType>standard</solderType>
          <effectiveCount count="3" />
          <fiducialMarkData>
            <fiducialMark index="0">
              <markName>FID1</markName>
              <markPosition x="-43" y="-53" />
            </fiducialMark>
            <fiducialMark index="1">
              <markName>FID2</markName>
              <markPosition x="53" y="-53" />
            </fiducialMark>
            <fiducialMark index="2">
              <markName>FID3</markName>
              <markPosition x="-43" y="63" />
            </fiducialMark>
          </fiducialMarkData>
        </bocMark>
        <secondBocMark no="1">
          <markType>NoUse</markType>
          <markName>BOCMARK01</markName>
          <solderType>standard</solderType>
          <effectiveCount count="0" />
          <fiducialMarkData>
            <fiducialMark index="0">
              <markName />
              <markPosition />
            </fiducialMark>
            <fiducialMark index="1">
              <markName />
              <markPosition />
            </fiducialMark>
            <fiducialMark index="2">
              <markName />
              <markPosition />
            </fiducialMark>
          </fiducialMarkData>
        </secondBocMark>
      </circuitData>
    </bocMarkData>
  </machine>
</productionProgram>
